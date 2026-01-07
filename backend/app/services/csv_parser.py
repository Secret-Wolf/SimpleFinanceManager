import csv
import hashlib
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..models import Transaction, Account, Import


# Volksbank CSV column mapping
VOLKSBANK_COLUMNS = {
    "Bezeichnung Auftragskonto": "account_name",
    "IBAN Auftragskonto": "account_iban",
    "BIC Auftragskonto": "account_bic",
    "Bankname Auftragskonto": "bank_name",
    "Buchungstag": "booking_date",
    "Valutadatum": "value_date",
    "Name Zahlungsbeteiligter": "counterpart_name",
    "IBAN Zahlungsbeteiligter": "counterpart_iban",
    "BIC (SWIFT-Code) Zahlungsbeteiligter": "counterpart_bic",
    "Buchungstext": "booking_type",
    "Verwendungszweck": "purpose",
    "Betrag": "amount",
    "Waehrung": "currency",
    "Saldo nach Buchung": "balance_after",
    "Kategorie": "original_category",
    "Glaeubiger ID": "creditor_id",
    "Mandatsreferenz": "mandate_reference",
}


def parse_german_date(date_str: str) -> Optional[datetime]:
    """Parse German date format DD.MM.YYYY"""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def parse_german_decimal(value_str: str) -> Optional[Decimal]:
    """Parse German decimal format (comma as decimal separator)"""
    if not value_str or not value_str.strip():
        return None
    try:
        # Replace German format: 1.234,56 -> 1234.56
        cleaned = value_str.strip().replace(".", "").replace(",", ".")
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def generate_import_hash(row: Dict) -> str:
    """Generate unique hash for duplicate detection"""
    # Hash from: booking_date + amount + counterpart_iban + purpose (first 50 chars)
    purpose = (row.get("purpose") or "")[:50]
    hash_input = f"{row.get('booking_date')}|{row.get('amount')}|{row.get('counterpart_iban', '')}|{purpose}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:32]


def detect_csv_format(content: str) -> str:
    """Detect which bank format the CSV is in"""
    first_line = content.split("\n")[0] if content else ""

    if "Bezeichnung Auftragskonto" in first_line:
        return "volksbank"
    # Add more formats here later

    return "unknown"


def parse_volksbank_csv(content: str) -> List[Dict]:
    """Parse Volksbank/Atruvia CSV format"""
    # Handle BOM if present
    if content.startswith("\ufeff"):
        content = content[1:]

    reader = csv.DictReader(io.StringIO(content), delimiter=";")

    rows = []
    for csv_row in reader:
        row = {}

        # Map columns
        for csv_col, db_col in VOLKSBANK_COLUMNS.items():
            value = csv_row.get(csv_col, "").strip()

            if db_col in ("booking_date", "value_date"):
                row[db_col] = parse_german_date(value)
            elif db_col in ("amount", "balance_after"):
                row[db_col] = parse_german_decimal(value)
            else:
                row[db_col] = value if value else None

        # Skip rows without required fields
        if row.get("booking_date") and row.get("amount") is not None:
            row["import_hash"] = generate_import_hash(row)
            rows.append(row)

    return rows


def ensure_account_exists(db: Session, iban: str, name: str = None, bic: str = None, bank_name: str = None) -> Optional[Account]:
    """Create account if it doesn't exist, return account or None"""
    if not iban:
        return None

    account = db.query(Account).filter(Account.iban == iban).first()
    if not account:
        account = Account(
            iban=iban,
            name=name or iban,
            bic=bic,
            bank_name=bank_name,
            account_type="giro"
        )
        db.add(account)
        db.flush()

    return account


def import_csv(db: Session, content: str, filename: str = None) -> Import:
    """Import CSV content and return import result"""
    # Detect format
    csv_format = detect_csv_format(content)

    if csv_format == "volksbank":
        rows = parse_volksbank_csv(content)
    else:
        # Try Volksbank as default
        rows = parse_volksbank_csv(content)

    # Track statistics
    total = len(rows)
    new_count = 0
    duplicate_count = 0
    error_count = 0

    # Ensure account exists first (only once)
    account = None
    if rows:
        first_row = rows[0]
        account = ensure_account_exists(
            db,
            first_row.get("account_iban"),
            first_row.get("account_name"),
            first_row.get("account_bic"),
            first_row.get("bank_name")
        )
        db.commit()  # Commit account creation

    for row in rows:
        try:
            # Check for duplicate in database
            existing = db.query(Transaction).filter(
                Transaction.import_hash == row["import_hash"]
            ).first()

            if existing:
                duplicate_count += 1
                continue

            # Create transaction
            transaction = Transaction(
                import_hash=row["import_hash"],
                account_id=account.id if account else None,
                account_name=row.get("account_name"),
                account_iban=row.get("account_iban"),
                account_bic=row.get("account_bic"),
                bank_name=row.get("bank_name"),
                booking_date=row["booking_date"],
                value_date=row.get("value_date"),
                counterpart_name=row.get("counterpart_name"),
                counterpart_iban=row.get("counterpart_iban"),
                counterpart_bic=row.get("counterpart_bic"),
                booking_type=row.get("booking_type"),
                purpose=row.get("purpose"),
                amount=row["amount"],
                currency=row.get("currency", "EUR"),
                balance_after=row.get("balance_after"),
                original_category=row.get("original_category"),
                creditor_id=row.get("creditor_id"),
                mandate_reference=row.get("mandate_reference"),
            )

            db.add(transaction)

            # Flush to detect duplicates immediately
            try:
                db.flush()
                new_count += 1
            except IntegrityError:
                db.rollback()
                duplicate_count += 1
                # Re-fetch account after rollback
                if account:
                    account = db.query(Account).filter(Account.id == account.id).first()

        except Exception as e:
            db.rollback()
            error_count += 1
            # Re-fetch account after rollback
            if account:
                account = db.query(Account).filter(Account.iban == row.get("account_iban")).first()
            continue

    # Commit all successful transactions
    db.commit()

    # Create import record
    status = "success"
    if error_count > 0 and new_count == 0:
        status = "failed"
    elif error_count > 0:
        status = "partial"

    import_record = Import(
        filename=filename,
        transactions_total=total,
        transactions_new=new_count,
        transactions_duplicate=duplicate_count,
        transactions_error=error_count,
        status=status
    )
    db.add(import_record)
    db.commit()

    return import_record
