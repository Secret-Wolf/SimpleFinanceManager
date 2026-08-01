import csv
import hashlib
import io
import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from .. import schemas
from ..audit import log_data_event
from ..auth import get_current_user
from ..database import get_db
from ..models import Account, Category, Tag, Transaction, User, transaction_tags
from ..services.attachments import delete_attachments_for_transactions
from ..services.category_tree import get_descendant_ids
from ..services.transfers import detect_transfers_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _csv_safe(value) -> str:
    """Neutralize CSV/formula injection: cells starting with = + - @ (or a control char)
    get a leading apostrophe so spreadsheet apps don't execute them as formulas.
    Note: only for text cells — never apply to numeric amounts (they can start with '-')."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


@router.get("", response_model=schemas.TransactionList)
def get_transactions(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=1000),
    sort_by: str = Query("booking_date", pattern="^(booking_date|amount|amount_abs|counterpart_name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category_id: Optional[int] = None,
    include_subcategories: bool = True,
    account_id: Optional[int] = None,
    account_iban: Optional[str] = None,
    shared_only: bool = False,
    transfers_only: bool = False,
    amount_type: Optional[str] = Query(None, pattern="^(income|expenses|all)$"),
    search: Optional[str] = None,
    uncategorized_only: bool = False,
    tag_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get paginated list of transactions with filters"""

    # User isolation: only show transactions from user's accounts
    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]
    logger.info(f"[Transactions] user={current_user.id} account_id={account_id} user_account_ids={user_account_ids}")

    # Basis-Query ohne Loader-Optionen — davon zweigen count()/sum() ab
    query = db.query(Transaction).filter(
        Transaction.is_split_parent == False,
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    )

    # Apply filters
    if start_date:
        query = query.filter(Transaction.booking_date >= start_date)

    if end_date:
        query = query.filter(Transaction.booking_date <= end_date)

    if category_id:
        if include_subcategories:
            # Get category and all its descendants (any depth)
            category_ids = [category_id] + get_descendant_ids(db, current_user.id, category_id)
            query = query.filter(Transaction.category_id.in_(category_ids))
        else:
            query = query.filter(Transaction.category_id == category_id)

    if uncategorized_only:
        # Umbuchungen brauchen keine Kategorie — hier ausblenden
        query = query.filter(Transaction.category_id == None, Transaction.is_transfer == False)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    elif account_iban:
        query = query.filter(Transaction.account_iban == account_iban)

    if shared_only:
        query = query.filter(Transaction.is_shared == True)

    if transfers_only:
        query = query.filter(Transaction.is_transfer == True)

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

    if tag_id:
        # Nur eigene Tags filtern (fremde Tag-IDs liefern eine leere Liste)
        tag = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == current_user.id).first()
        if tag:
            query = query.join(
                transaction_tags, Transaction.id == transaction_tags.c.transaction_id
            ).filter(transaction_tags.c.tag_id == tag.id)
        else:
            query = query.filter(Transaction.id == -1)

    # Get total count + Summe aller Treffer (über alle Seiten, z.B. für Tag-Auswertungen)
    total = query.count()
    total_amount = query.with_entities(func.sum(Transaction.amount)).scalar() or Decimal("0")
    logger.info(f"[Transactions] account_id={account_id} total_results={total}")

    # Apply sorting
    if sort_by == "booking_date":
        order_col = Transaction.booking_date
    elif sort_by == "amount":
        order_col = Transaction.amount
    elif sort_by == "amount_abs":
        # Betrag der Höhe nach, unabhängig vom Vorzeichen (größte Einnahme/Ausgabe zuerst)
        order_col = func.abs(Transaction.amount)
    elif sort_by == "counterpart_name":
        order_col = Transaction.counterpart_name
    else:
        order_col = Transaction.booking_date

    if sort_order == "desc":
        query = query.order_by(order_col.desc(), Transaction.id.desc())
    else:
        query = query.order_by(order_col.asc(), Transaction.id.asc())

    # Pagination (Loader-Optionen erst hier — count()/sum() oben brauchen sie nicht)
    offset = (page - 1) * per_page
    transactions = query.options(
        joinedload(Transaction.category),
        selectinload(Transaction.tags),
        selectinload(Transaction.attachments),
    ).offset(offset).limit(per_page).all()

    pages = (total + per_page - 1) // per_page

    return schemas.TransactionList(
        items=transactions,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        total_amount=total_amount,
    )


@router.get("/export")
def export_transactions(
    account_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export transactions as CSV"""
    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    query = db.query(Transaction).options(
        joinedload(Transaction.category),
        selectinload(Transaction.tags),
    ).filter(
        Transaction.is_split_parent == False,
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    )

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if start_date:
        query = query.filter(Transaction.booking_date >= start_date)
    if end_date:
        query = query.filter(Transaction.booking_date <= end_date)

    transactions = query.order_by(Transaction.booking_date.desc(), Transaction.id.desc()).all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow([
        'Datum', 'Wertstellung', 'Empfänger/Auftraggeber', 'IBAN', 'BIC',
        'Buchungsart', 'Verwendungszweck', 'Betrag', 'Währung', 'Saldo danach',
        'Kategorie', 'Konto', 'Bank', 'Gemeinsam', 'Umbuchung', 'Tags', 'Notizen'
    ])

    for tx in transactions:
        cat_name = tx.category.name if tx.category else ''
        writer.writerow([
            tx.booking_date.isoformat() if tx.booking_date else '',
            tx.value_date.isoformat() if tx.value_date else '',
            _csv_safe(tx.counterpart_name),
            _csv_safe(tx.counterpart_iban),
            _csv_safe(tx.counterpart_bic),
            _csv_safe(tx.booking_type),
            _csv_safe(tx.purpose),
            str(tx.amount) if tx.amount is not None else '',
            tx.currency or 'EUR',
            str(tx.balance_after) if tx.balance_after is not None else '',
            _csv_safe(cat_name),
            _csv_safe(tx.account_name),
            _csv_safe(tx.bank_name),
            'Ja' if tx.is_shared else 'Nein',
            'Ja' if tx.is_transfer else 'Nein',
            _csv_safe(', '.join(t.name for t in tx.tags)),
            _csv_safe(tx.notes)
        ])

    csv_content = output.getvalue()
    output.close()

    # Use BOM for Excel compatibility
    bom = '\ufeff'
    filename = f"transaktionen-export-{date.today().isoformat()}.csv"

    return StreamingResponse(
        iter([bom + csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/{transaction_id}", response_model=schemas.Transaction)
def get_transaction(transaction_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get single transaction by ID"""
    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    transaction = db.query(Transaction).options(
        joinedload(Transaction.category),
        joinedload(Transaction.split_children),
        selectinload(Transaction.tags),
        selectinload(Transaction.attachments),
    ).filter(
        Transaction.id == transaction_id,
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    return transaction


@router.patch("/{transaction_id}", response_model=schemas.Transaction)
def update_transaction(
    transaction_id: int,
    update: schemas.TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update transaction (category, notes, tags)"""
    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    if update.category_id is not None:
        # Verify category exists
        if update.category_id != 0:
            category = db.query(Category).filter(
                Category.id == update.category_id,
                Category.user_id == current_user.id,
            ).first()
            if not category:
                raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")
            transaction.category_id = update.category_id
        else:
            transaction.category_id = None

    if update.notes is not None:
        transaction.notes = update.notes

    if update.is_shared is not None:
        transaction.is_shared = update.is_shared
        if not update.is_shared:
            transaction.shared_household_id = None

    if update.is_transfer is not None:
        transaction.is_transfer = update.is_transfer

    if update.shared_household_id is not None:
        transaction.shared_household_id = update.shared_household_id if update.shared_household_id != 0 else None

    if update.amount is not None:
        transaction.amount = update.amount

    if update.counterpart_name is not None:
        transaction.counterpart_name = update.counterpart_name

    if update.purpose is not None:
        transaction.purpose = update.purpose

    if update.booking_date is not None:
        transaction.booking_date = update.booking_date
        transaction.value_date = update.booking_date

    if update.tag_ids is not None:
        # Ersetzt die komplette Tag-Zuweisung; nur eigene Tags erlaubt
        unique_ids = list(dict.fromkeys(update.tag_ids))
        tags = db.query(Tag).filter(
            Tag.id.in_(unique_ids), Tag.user_id == current_user.id
        ).all() if unique_ids else []
        if len(tags) != len(unique_ids):
            raise HTTPException(status_code=400, detail="Tag nicht gefunden")
        transaction.tags = tags

    db.commit()
    db.refresh(transaction)

    return transaction


@router.post("/{transaction_id}/split", response_model=List[schemas.Transaction])
def split_transaction(
    transaction_id: int,
    split_data: schemas.SplitTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Split a transaction into multiple parts"""
    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    ).first()

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
        category = db.query(Category).filter(
            Category.id == part.category_id,
            Category.user_id == current_user.id,
        ).first()
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
def delete_transaction(transaction_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete a transaction"""
    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    child_ids = []
    if transaction.is_split_parent:
        child_ids = [
            t.id for t in db.query(Transaction.id).filter(
                Transaction.parent_transaction_id == transaction_id
            ).all()
        ]

    # Belege (DB-Zeilen + Dateien) für die Transaktion und etwaige Split-Kinder entfernen
    delete_attachments_for_transactions(db, [transaction_id] + child_ids)

    # Tag-Zuweisungen der Split-Kinder per Bulk räumen (das Bulk-Delete unten läuft an
    # ORM-Kaskaden vorbei); die eigene Zuweisung entfernt das ORM bei db.delete() selbst
    if child_ids:
        db.execute(transaction_tags.delete().where(transaction_tags.c.transaction_id.in_(child_ids)))

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

    log_data_event(
        "delete",
        user_id=current_user.id,
        resource="transaction",
        resource_id=transaction_id,
    )

    return {"message": "Transaktion gelöscht"}


@router.post("/detect-transfers")
def detect_transfers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Markiert Buchungen zwischen eigenen Konten als Umbuchung (is_transfer).
    Läuft auch automatisch nach jedem CSV-/FinTS-Import."""
    count = detect_transfers_for_user(db, current_user.id)
    return {
        "message": f"{count} Umbuchungen erkannt",
        "detected_count": count
    }


@router.post("/bulk-categorize")
def bulk_categorize(
    transaction_ids: List[int],
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign category to multiple transactions"""
    # Verify category exists
    if category_id != 0:
        category = db.query(Category).filter(
            Category.id == category_id,
            Category.user_id == current_user.id,
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")

    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    updated = db.query(Transaction).filter(
        Transaction.id.in_(transaction_ids),
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    ).update(
        {"category_id": category_id if category_id != 0 else None},
        synchronize_session=False
    )

    db.commit()

    return {"message": f"{updated} Transaktionen aktualisiert"}


@router.post("/bulk-shared")
def bulk_set_shared(
    data: schemas.BulkSharedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set shared flag on multiple transactions"""
    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    updated = db.query(Transaction).filter(
        Transaction.id.in_(data.transaction_ids),
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    ).update(
        {"is_shared": data.is_shared},
        synchronize_session=False
    )

    db.commit()

    label = "als gemeinsam markiert" if data.is_shared else "als persönlich markiert"
    return {"message": f"{updated} Transaktionen {label}", "updated_count": updated}


@router.post("/bulk-tag")
def bulk_tag(
    data: schemas.BulkTagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fügt ein Tag mehreren Transaktionen hinzu bzw. entfernt es (additiv,
    bestehende andere Tag-Zuweisungen bleiben unberührt)."""
    tag = db.query(Tag).filter(Tag.id == data.tag_id, Tag.user_id == current_user.id).first()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag nicht gefunden")

    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    transactions = db.query(Transaction).options(selectinload(Transaction.tags)).filter(
        Transaction.id.in_(data.transaction_ids),
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    ).all()

    updated = 0
    for tx in transactions:
        if data.remove:
            if tag in tx.tags:
                tx.tags.remove(tag)
                updated += 1
        else:
            if tag not in tx.tags:
                tx.tags.append(tag)
                updated += 1

    db.commit()

    label = f'Tag "{tag.name}" entfernt' if data.remove else f'Tag "{tag.name}" zugewiesen'
    return {"message": f"{updated} Transaktionen: {label}", "updated_count": updated}


@router.post("/manual", response_model=schemas.Transaction)
def create_manual_transaction(
    data: schemas.ManualTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erstellt eine manuelle Transaktion (Bargeld, Geschenke, etc.)"""

    # Determine target account
    if data.account_id:
        # Use specified account - verify ownership
        target_account = db.query(Account).filter(
            Account.id == data.account_id, Account.user_id == current_user.id
        ).first()
        if not target_account:
            raise HTTPException(status_code=404, detail="Konto nicht gefunden")
    else:
        # Fallback: Bargeld-Account erstellen oder finden (per User)
        cash_iban = f"CASH{current_user.id:016d}"
        target_account = db.query(Account).filter(
            Account.iban == cash_iban, Account.user_id == current_user.id
        ).first()

        if not target_account:
            target_account = Account(
                name="Bargeld",
                iban=cash_iban,
                bank_name="Manuell",
                account_type="cash",
                user_id=current_user.id,
            )
            db.add(target_account)
            db.flush()

    # Kategorie validieren falls angegeben
    if data.category_id:
        category = db.query(Category).filter(
            Category.id == data.category_id,
            Category.user_id == current_user.id,
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Kategorie nicht gefunden")

    # Eindeutigen Hash generieren
    import_hash = f"manual_{uuid.uuid4().hex[:24]}"

    # Transaktion erstellen
    transaction = Transaction(
        import_hash=import_hash,
        account_id=target_account.id,
        account_name=target_account.name,
        account_iban=target_account.iban,
        bank_name=target_account.bank_name or "Manuell",
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

    log_data_event(
        "create",
        user_id=current_user.id,
        resource="manual_transaction",
        resource_id=transaction.id,
        detail=f"amount={data.amount} description={data.description}",
    )

    return transaction
