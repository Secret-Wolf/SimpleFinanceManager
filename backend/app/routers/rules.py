from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List

from ..database import get_db
from ..models import CategorizationRule, Category, Transaction
from ..services.categorizer import apply_rules_to_uncategorized, create_rule_from_transaction
from .. import schemas

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=List[schemas.Rule])
def get_rules(db: Session = Depends(get_db)):
    """Get all categorization rules"""
    rules = db.query(CategorizationRule).options(
        joinedload(CategorizationRule.category)
    ).order_by(CategorizationRule.priority.desc()).all()

    return rules


@router.get("/{rule_id}", response_model=schemas.Rule)
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    """Get single rule"""
    rule = db.query(CategorizationRule).options(
        joinedload(CategorizationRule.category)
    ).filter(CategorizationRule.id == rule_id).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    return rule


@router.post("", response_model=schemas.Rule)
def create_rule(
    rule_data: schemas.RuleCreate,
    db: Session = Depends(get_db)
):
    """Create new categorization rule"""

    # Verify category exists
    category = db.query(Category).filter(Category.id == rule_data.assign_category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")

    # At least one matching criterion must be set
    has_criteria = any([
        rule_data.match_counterpart_name,
        rule_data.match_counterpart_iban,
        rule_data.match_purpose,
        rule_data.match_booking_type,
        rule_data.match_amount_min is not None,
        rule_data.match_amount_max is not None
    ])

    if not has_criteria:
        raise HTTPException(
            status_code=400,
            detail="Mindestens ein Matching-Kriterium erforderlich"
        )

    rule = CategorizationRule(
        name=rule_data.name,
        priority=rule_data.priority,
        match_counterpart_name=rule_data.match_counterpart_name,
        match_counterpart_iban=rule_data.match_counterpart_iban,
        match_purpose=rule_data.match_purpose,
        match_booking_type=rule_data.match_booking_type,
        match_amount_min=rule_data.match_amount_min,
        match_amount_max=rule_data.match_amount_max,
        assign_category_id=rule_data.assign_category_id,
        assign_shared=rule_data.assign_shared,
        is_active=rule_data.is_active
    )

    db.add(rule)
    db.commit()
    db.refresh(rule)

    # Load category for response
    rule = db.query(CategorizationRule).options(
        joinedload(CategorizationRule.category)
    ).filter(CategorizationRule.id == rule.id).first()

    return rule


@router.patch("/{rule_id}", response_model=schemas.Rule)
def update_rule(
    rule_id: int,
    update: schemas.RuleUpdate,
    db: Session = Depends(get_db)
):
    """Update rule"""
    rule = db.query(CategorizationRule).filter(CategorizationRule.id == rule_id).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    if update.name is not None:
        rule.name = update.name

    if update.priority is not None:
        rule.priority = update.priority

    if update.match_counterpart_name is not None:
        rule.match_counterpart_name = update.match_counterpart_name or None

    if update.match_counterpart_iban is not None:
        rule.match_counterpart_iban = update.match_counterpart_iban or None

    if update.match_purpose is not None:
        rule.match_purpose = update.match_purpose or None

    if update.match_booking_type is not None:
        rule.match_booking_type = update.match_booking_type or None

    if update.match_amount_min is not None:
        rule.match_amount_min = update.match_amount_min

    if update.match_amount_max is not None:
        rule.match_amount_max = update.match_amount_max

    if update.assign_category_id is not None:
        category = db.query(Category).filter(Category.id == update.assign_category_id).first()
        if not category:
            raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")
        rule.assign_category_id = update.assign_category_id

    if update.assign_shared is not None:
        rule.assign_shared = update.assign_shared

    if update.is_active is not None:
        rule.is_active = update.is_active

    db.commit()
    db.refresh(rule)

    # Load category for response
    rule = db.query(CategorizationRule).options(
        joinedload(CategorizationRule.category)
    ).filter(CategorizationRule.id == rule.id).first()

    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    """Delete rule"""
    rule = db.query(CategorizationRule).filter(CategorizationRule.id == rule_id).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    db.delete(rule)
    db.commit()

    return {"message": "Regel gelöscht"}


@router.post("/apply")
def apply_rules(db: Session = Depends(get_db)):
    """Apply all rules to uncategorized transactions"""
    count = apply_rules_to_uncategorized(db)

    return {
        "message": f"{count} Transaktionen kategorisiert",
        "categorized_count": count
    }


@router.post("/from-transaction/{transaction_id}", response_model=schemas.Rule)
def create_rule_from_tx(
    transaction_id: int,
    category_id: int,
    match_type: str = "counterpart_name",
    db: Session = Depends(get_db)
):
    """Create rule based on a transaction"""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    # Verify category exists
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")

    valid_types = ["counterpart_name", "counterpart_iban", "purpose", "booking_type"]
    if match_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Match-Typ. Erlaubt: {', '.join(valid_types)}"
        )

    rule = create_rule_from_transaction(db, transaction, category_id, match_type)

    # Load category for response
    rule = db.query(CategorizationRule).options(
        joinedload(CategorizationRule.category)
    ).filter(CategorizationRule.id == rule.id).first()

    return rule
