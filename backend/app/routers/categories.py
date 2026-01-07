from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from ..database import get_db
from ..models import Category, Transaction
from .. import schemas

router = APIRouter(prefix="/api/categories", tags=["categories"])


def build_category_tree(categories: List[Category], parent_id: Optional[int] = None) -> List[dict]:
    """Build hierarchical category tree"""
    tree = []

    for cat in categories:
        if cat.parent_id == parent_id:
            children = build_category_tree(categories, cat.id)
            cat_dict = {
                "id": cat.id,
                "name": cat.name,
                "parent_id": cat.parent_id,
                "full_path": cat.full_path,
                "color": cat.color,
                "icon": cat.icon,
                "budget_monthly": cat.budget_monthly,
                "created_at": cat.created_at,
                "transaction_count": cat.transaction_count if hasattr(cat, "transaction_count") else 0,
                "children": children
            }
            tree.append(cat_dict)

    return tree


def update_full_path(db: Session, category: Category):
    """Update full_path for category and all its children"""
    if category.parent_id:
        parent = db.query(Category).filter(Category.id == category.parent_id).first()
        if parent:
            category.full_path = f"{parent.full_path}:{category.name}" if parent.full_path else f"{parent.name}:{category.name}"
        else:
            category.full_path = category.name
    else:
        category.full_path = category.name

    # Update children recursively
    children = db.query(Category).filter(Category.parent_id == category.id).all()
    for child in children:
        update_full_path(db, child)


@router.get("", response_model=List[dict])
def get_categories(
    flat: bool = Query(False, description="Return flat list instead of tree"),
    db: Session = Depends(get_db)
):
    """Get all categories as tree or flat list"""

    # Get categories with transaction count
    categories = db.query(
        Category,
        func.count(Transaction.id).label("transaction_count")
    ).outerjoin(
        Transaction,
        Transaction.category_id == Category.id
    ).group_by(Category.id).all()

    # Add transaction_count to category objects
    result = []
    for cat, count in categories:
        cat.transaction_count = count
        result.append(cat)

    if flat:
        return [
            {
                "id": c.id,
                "name": c.name,
                "parent_id": c.parent_id,
                "full_path": c.full_path,
                "color": c.color,
                "icon": c.icon,
                "budget_monthly": c.budget_monthly,
                "created_at": c.created_at,
                "transaction_count": c.transaction_count
            }
            for c in result
        ]

    return build_category_tree(result)


@router.get("/{category_id}", response_model=schemas.Category)
def get_category(category_id: int, db: Session = Depends(get_db)):
    """Get single category"""
    category = db.query(Category).filter(Category.id == category_id).first()

    if not category:
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden")

    # Get transaction count
    count = db.query(func.count(Transaction.id)).filter(
        Transaction.category_id == category_id
    ).scalar()

    category.transaction_count = count

    return category


@router.post("", response_model=schemas.Category)
def create_category(
    category_data: schemas.CategoryCreate,
    db: Session = Depends(get_db)
):
    """Create new category"""

    # Check for duplicate name under same parent
    existing = db.query(Category).filter(
        Category.name == category_data.name,
        Category.parent_id == category_data.parent_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Kategorie mit diesem Namen existiert bereits"
        )

    # Verify parent exists if specified
    if category_data.parent_id:
        parent = db.query(Category).filter(Category.id == category_data.parent_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Elternkategorie nicht gefunden")

        # Check max depth (2 levels)
        if parent.parent_id:
            raise HTTPException(
                status_code=400,
                detail="Maximale Verschachtelungstiefe erreicht (2 Ebenen)"
            )

    category = Category(
        name=category_data.name,
        parent_id=category_data.parent_id,
        color=category_data.color,
        icon=category_data.icon,
        budget_monthly=category_data.budget_monthly
    )

    db.add(category)
    db.flush()

    update_full_path(db, category)
    db.commit()
    db.refresh(category)

    category.transaction_count = 0
    return category


@router.patch("/{category_id}", response_model=schemas.Category)
def update_category(
    category_id: int,
    update: schemas.CategoryUpdate,
    db: Session = Depends(get_db)
):
    """Update category"""
    category = db.query(Category).filter(Category.id == category_id).first()

    if not category:
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden")

    if update.name is not None:
        # Check for duplicate
        existing = db.query(Category).filter(
            Category.name == update.name,
            Category.parent_id == category.parent_id,
            Category.id != category_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Kategorie mit diesem Namen existiert bereits"
            )

        category.name = update.name

    if update.parent_id is not None:
        # Prevent circular reference
        if update.parent_id == category_id:
            raise HTTPException(status_code=400, detail="Kategorie kann nicht eigene Elternkategorie sein")

        # Check if new parent is a child of this category
        if update.parent_id:
            child_ids = [c.id for c in db.query(Category).filter(Category.parent_id == category_id).all()]
            if update.parent_id in child_ids:
                raise HTTPException(status_code=400, detail="Zirkuläre Referenz nicht erlaubt")

            parent = db.query(Category).filter(Category.id == update.parent_id).first()
            if not parent:
                raise HTTPException(status_code=400, detail="Elternkategorie nicht gefunden")

            # Check max depth
            if parent.parent_id:
                raise HTTPException(
                    status_code=400,
                    detail="Maximale Verschachtelungstiefe erreicht (2 Ebenen)"
                )

        category.parent_id = update.parent_id if update.parent_id != 0 else None

    if update.color is not None:
        category.color = update.color

    if update.icon is not None:
        category.icon = update.icon

    if update.budget_monthly is not None:
        category.budget_monthly = update.budget_monthly

    update_full_path(db, category)
    db.commit()
    db.refresh(category)

    # Get transaction count
    count = db.query(func.count(Transaction.id)).filter(
        Transaction.category_id == category_id
    ).scalar()

    category.transaction_count = count

    return category


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    move_to_category_id: Optional[int] = Query(None, description="Move transactions to this category"),
    db: Session = Depends(get_db)
):
    """Delete category, optionally moving transactions to another category"""
    category = db.query(Category).filter(Category.id == category_id).first()

    if not category:
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden")

    # Check for children
    children = db.query(Category).filter(Category.parent_id == category_id).count()
    if children > 0:
        raise HTTPException(
            status_code=400,
            detail="Kategorie hat Unterkategorien. Bitte diese zuerst löschen oder verschieben."
        )

    # Move or uncategorize transactions
    if move_to_category_id:
        target = db.query(Category).filter(Category.id == move_to_category_id).first()
        if not target:
            raise HTTPException(status_code=400, detail="Zielkategorie nicht gefunden")

        db.query(Transaction).filter(
            Transaction.category_id == category_id
        ).update({"category_id": move_to_category_id}, synchronize_session=False)
    else:
        db.query(Transaction).filter(
            Transaction.category_id == category_id
        ).update({"category_id": None}, synchronize_session=False)

    # Delete rules using this category
    from ..models import CategorizationRule
    db.query(CategorizationRule).filter(
        CategorizationRule.assign_category_id == category_id
    ).delete()

    db.delete(category)
    db.commit()

    return {"message": "Kategorie gelöscht"}


@router.post("/init-defaults")
def init_default_categories(db: Session = Depends(get_db)):
    """Initialize default categories"""

    # Check if categories already exist
    existing = db.query(Category).count()
    if existing > 0:
        return {"message": "Kategorien existieren bereits", "count": existing}

    default_categories = [
        # Einnahmen
        {"name": "Einnahmen", "color": "#4CAF50"},
        {"name": "Gehalt", "parent": "Einnahmen", "color": "#66BB6A"},
        {"name": "Kindergeld", "parent": "Einnahmen", "color": "#81C784"},
        {"name": "Erstattungen", "parent": "Einnahmen", "color": "#A5D6A7"},
        {"name": "Sonstige Einnahmen", "parent": "Einnahmen", "color": "#C8E6C9"},

        # Wohnen
        {"name": "Wohnen", "color": "#2196F3"},
        {"name": "Miete", "parent": "Wohnen", "color": "#42A5F5"},
        {"name": "Strom", "parent": "Wohnen", "color": "#64B5F6"},
        {"name": "Gas", "parent": "Wohnen", "color": "#90CAF9"},
        {"name": "Internet", "parent": "Wohnen", "color": "#BBDEFB"},
        {"name": "Einrichtung", "parent": "Wohnen", "color": "#E3F2FD"},

        # Mobilität
        {"name": "Mobilität", "color": "#FF9800"},
        {"name": "Tanken", "parent": "Mobilität", "color": "#FFA726"},
        {"name": "Laden (E-Auto)", "parent": "Mobilität", "color": "#FFB74D"},
        {"name": "Versicherung (Auto)", "parent": "Mobilität", "color": "#FFCC80"},
        {"name": "Wartung", "parent": "Mobilität", "color": "#FFE0B2"},
        {"name": "ÖPNV", "parent": "Mobilität", "color": "#FFF3E0"},

        # Lebensmittel
        {"name": "Lebensmittel", "color": "#8BC34A"},
        {"name": "Supermarkt", "parent": "Lebensmittel", "color": "#9CCC65"},
        {"name": "Bäckerei", "parent": "Lebensmittel", "color": "#AED581"},
        {"name": "Restaurant", "parent": "Lebensmittel", "color": "#C5E1A5"},

        # Freizeit
        {"name": "Freizeit", "color": "#E91E63"},
        {"name": "Technik", "parent": "Freizeit", "color": "#EC407A"},
        {"name": "Bücher", "parent": "Freizeit", "color": "#F06292"},
        {"name": "Gaming", "parent": "Freizeit", "color": "#F48FB1"},
        {"name": "Streaming", "parent": "Freizeit", "color": "#F8BBD9"},
        {"name": "Ausgehen", "parent": "Freizeit", "color": "#FCE4EC"},

        # Finanzen
        {"name": "Finanzen", "color": "#9C27B0"},
        {"name": "Sparen", "parent": "Finanzen", "color": "#AB47BC"},
        {"name": "Investment", "parent": "Finanzen", "color": "#BA68C8"},
        {"name": "Versicherung", "parent": "Finanzen", "color": "#CE93D8"},
        {"name": "Bausparen", "parent": "Finanzen", "color": "#E1BEE7"},

        # Abos & Verträge
        {"name": "Abos & Verträge", "color": "#00BCD4"},
        {"name": "Mobilfunk", "parent": "Abos & Verträge", "color": "#26C6DA"},
        {"name": "Software", "parent": "Abos & Verträge", "color": "#4DD0E1"},

        # Sonstiges
        {"name": "Sonstiges", "color": "#607D8B"},
        {"name": "Unkategorisiert", "parent": "Sonstiges", "color": "#78909C"},
    ]

    # First pass: create parent categories
    parent_map = {}
    for cat_data in default_categories:
        if "parent" not in cat_data:
            category = Category(
                name=cat_data["name"],
                color=cat_data.get("color"),
                full_path=cat_data["name"]
            )
            db.add(category)
            db.flush()
            parent_map[cat_data["name"]] = category.id

    # Second pass: create child categories
    for cat_data in default_categories:
        if "parent" in cat_data:
            parent_id = parent_map.get(cat_data["parent"])
            if parent_id:
                category = Category(
                    name=cat_data["name"],
                    parent_id=parent_id,
                    color=cat_data.get("color"),
                    full_path=f"{cat_data['parent']}:{cat_data['name']}"
                )
                db.add(category)

    db.commit()

    return {"message": "Standardkategorien erstellt", "count": len(default_categories)}
