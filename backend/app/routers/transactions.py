from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from typing import Optional, List
from datetime import date
from decimal import Decimal
import hashlib
import uuid

from ..database import get_db
from ..models import Transaction, Category, Account
from .. import schemas

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=schemas.TransactionList)
def get_transactions(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("booking_date", regex="^(booking_date|amount|counterpart_name|category)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category_id: Optional[int] = None,
    include_subcategories: bool = True,
    account_id: Optional[int] = None,
    account_iban: Optional[str] = None,
    profile_id: Optional[int] = None,
    shared_only: bool = False,
    amount_type: Optional[str] = Query(None, regex="^(income|expenses|all)$"),
    search: Optional[str] = None,
    uncategorized_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get paginated list of transactions with filters"""

    query = db.query(Transaction).options(
        joinedload(Transaction.category)
    ).filter(Transaction.is_split_parent == False)

    # Apply filters
    if start_date:
        query = query.filter(Transaction.booking_date >= start_date)

    if end_date:
        query = query.filter(Transaction.booking_date <= end_date)

    if category_id:
        if include_subcategories:
            # Get category and all its children
            category_ids = [category_id]
            children = db.query(Category.id).filter(Category.parent_id == category_id).all()
            category_ids.extend([c.id for c in children])
            query = query.filter(Transaction.category_id.in_(category_ids))
        else:
            query = query.filter(Transaction.category_id == category_id)

    if uncategorized_only:
        query = query.filter(Transaction.category_id == None)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    elif account_iban:
        query = query.filter(Transaction.account_iban == account_iban)

    # Profile filter: show transactions from accounts belonging to this profile
    if profile_id:
        profile_account_ids = [a.id for a in db.query(Account.id).filter(Account.profile_id == profile_id).all()]
        if profile_account_ids:
            query = query.filter(Transaction.account_id.in_(profile_account_ids))
        else:
            query = query.filter(Transaction.id == -1)  # No results

    if shared_only:
        query = query.filter(Transaction.is_shared == True)

    if amount_type == "income":
        query = query.filter(Transaction.amount > 0)
    elif amount_type == "expenses":
        query = query.filter(Transaction.amount < 0)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Transaction.counterpart_name.ilike(search_pattern),
                Transaction.purpose.ilike(search_pattern),
                Transaction.notes.ilike(search_pattern)
            )
        )

    # Get total count
    total = query.count()

    # Apply sorting
    if sort_by == "booking_date":
        order_col = Transaction.booking_date
    elif sort_by == "amount":
        order_col = Transaction.amount
    elif sort_by == "counterpart_name":
        order_col = Transaction.counterpart_name
    else:
        order_col = Transaction.booking_date

    if sort_order == "desc":
        query = query.order_by(order_col.desc(), Transaction.id.desc())
    else:
        query = query.order_by(order_col.asc(), Transaction.id.asc())

    # Pagination
    offset = (page - 1) * per_page
    transactions = query.offset(offset).limit(per_page).all()

    pages = (total + per_page - 1) // per_page

    return schemas.TransactionList(
        items=transactions,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages
    )


@router.get("/{transaction_id}", response_model=schemas.Transaction)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Get single transaction by ID"""
    transaction = db.query(Transaction).options(
        joinedload(Transaction.category),
        joinedload(Transaction.split_children)
    ).filter(Transaction.id == transaction_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    return transaction


@router.patch("/{transaction_id}", response_model=schemas.Transaction)
def update_transaction(
    transaction_id: int,
    update: schemas.TransactionUpdate,
    db: Session = Depends(get_db)
):
    """Update transaction (category, notes, tags)"""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    if update.category_id is not None:
        # Verify category exists
        if update.category_id != 0:
            category = db.query(Category).filter(Category.id == update.category_id).first()
            if not category:
                raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")
            transaction.category_id = update.category_id
        else:
            transaction.category_id = None

    if update.notes is not None:
        transaction.notes = update.notes

    if update.tags is not None:
        transaction.tags = update.tags

    if update.is_shared is not None:
        transaction.is_shared = update.is_shared

    db.commit()
    db.refresh(transaction)

    return transaction


@router.post("/{transaction_id}/split", response_model=List[schemas.Transaction])
def split_transaction(
    transaction_id: int,
    split_data: schemas.SplitTransactionCreate,
    db: Session = Depends(get_db)
):
    """Split a transaction into multiple parts"""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    if transaction.is_split_parent:
        raise HTTPException(status_code=400, detail="Transaktion ist bereits aufgeteilt")

    if transaction.parent_transaction_id:
        raise HTTPException(status_code=400, detail="Teil einer Splitbuchung kann nicht weiter aufgeteilt werden")

    # Validate split amounts
    total_split = sum(part.amount for part in split_data.parts)
    original_amount = abs(transaction.amount)

    if abs(total_split - original_amount) > Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail=f"Summe der Teile ({total_split}) stimmt nicht mit Originalbetrag ({original_amount}) überein"
        )

    # Mark original as split parent
    transaction.is_split_parent = True
    transaction.category_id = None

    # Create split children
    split_transactions = []
    is_expense = transaction.amount < 0

    for i, part in enumerate(split_data.parts):
        # Verify category exists
        category = db.query(Category).filter(Category.id == part.category_id).first()
        if not category:
            raise HTTPException(status_code=400, detail=f"Kategorie {part.category_id} nicht gefunden")

        # Generate unique hash for split
        split_hash = hashlib.sha256(
            f"{transaction.import_hash}:split:{i}".encode()
        ).hexdigest()[:32]

        # Amount should be negative for expenses
        split_amount = -part.amount if is_expense else part.amount

        split_tx = Transaction(
            import_hash=split_hash,
            parent_transaction_id=transaction.id,
            account_id=transaction.account_id,
            account_name=transaction.account_name,
            account_iban=transaction.account_iban,
            account_bic=transaction.account_bic,
            bank_name=transaction.bank_name,
            booking_date=transaction.booking_date,
            value_date=transaction.value_date,
            counterpart_name=transaction.counterpart_name,
            counterpart_iban=transaction.counterpart_iban,
            counterpart_bic=transaction.counterpart_bic,
            booking_type=transaction.booking_type,
            purpose=f"[Split] {transaction.purpose}" if transaction.purpose else "[Split]",
            amount=split_amount,
            currency=transaction.currency,
            category_id=part.category_id,
            notes=part.notes
        )

        db.add(split_tx)
        split_transactions.append(split_tx)

    db.commit()

    for tx in split_transactions:
        db.refresh(tx)

    return split_transactions


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Delete a transaction"""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    # If this is a split parent, also delete children
    if transaction.is_split_parent:
        db.query(Transaction).filter(
            Transaction.parent_transaction_id == transaction_id
        ).delete()

    # If this is a split child, check if we should unsplit the parent
    if transaction.parent_transaction_id:
        siblings = db.query(Transaction).filter(
            Transaction.parent_transaction_id == transaction.parent_transaction_id,
            Transaction.id != transaction_id
        ).count()

        if siblings == 0:
            # Last split child, unsplit parent
            parent = db.query(Transaction).filter(
                Transaction.id == transaction.parent_transaction_id
            ).first()
            if parent:
                parent.is_split_parent = False

    db.delete(transaction)
    db.commit()

    return {"message": "Transaktion gelöscht"}


@router.post("/bulk-categorize")
def bulk_categorize(
    transaction_ids: List[int],
    category_id: int,
    db: Session = Depends(get_db)
):
    """Assign category to multiple transactions"""
    # Verify category exists
    if category_id != 0:
        category = db.query(Category).filter(Category.id == category_id).first()
        if not category:
            raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")

    updated = db.query(Transaction).filter(
        Transaction.id.in_(transaction_ids)
    ).update(
        {"category_id": category_id if category_id != 0 else None},
        synchronize_session=False
    )

    db.commit()

    return {"message": f"{updated} Transaktionen aktualisiert"}


@router.post("/bulk-shared")
def bulk_set_shared(
    data: schemas.BulkSharedRequest,
    db: Session = Depends(get_db)
):
    """Set shared flag on multiple transactions"""
    updated = db.query(Transaction).filter(
        Transaction.id.in_(data.transaction_ids)
    ).update(
        {"is_shared": data.is_shared},
        synchronize_session=False
    )

    db.commit()

    label = "als gemeinsam markiert" if data.is_shared else "als persönlich markiert"
    return {"message": f"{updated} Transaktionen {label}", "updated_count": updated}


@router.post("/manual", response_model=schemas.Transaction)
def create_manual_transaction(
    data: schemas.ManualTransactionCreate,
    db: Session = Depends(get_db)
):
    """Erstellt eine manuelle Transaktion (Bargeld, Geschenke, etc.)"""

    # Bargeld-Account erstellen oder finden
    cash_iban = "CASH0000000000000000"
    cash_account = db.query(Account).filter(Account.iban == cash_iban).first()

    if not cash_account:
        cash_account = Account(
            name="Bargeld",
            iban=cash_iban,
            bank_name="Manuell",
            account_type="cash"
        )
        db.add(cash_account)
        db.flush()

    # Kategorie validieren falls angegeben
    if data.category_id:
        category = db.query(Category).filter(Category.id == data.category_id).first()
        if not category:
            raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")

    # Eindeutigen Hash generieren
    import_hash = f"manual_{uuid.uuid4().hex[:24]}"

    # Transaktion erstellen
    transaction = Transaction(
        import_hash=import_hash,
        account_id=cash_account.id,
        account_name=cash_account.name,
        account_iban=cash_iban,
        bank_name="Manuell",
        booking_date=data.booking_date,
        value_date=data.booking_date,
        counterpart_name=data.description,
        booking_type="Manuelle Buchung",
        purpose=data.description,
        amount=data.amount,
        currency="EUR",
        category_id=data.category_id,
        notes=data.notes
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction
