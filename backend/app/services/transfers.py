"""Umbuchungs-Erkennung: Buchungen zwischen eigenen Konten desselben Users.

Eine Transaktion gilt als Umbuchung, wenn die Gegenseiten-IBAN zu einem
eigenen Konto des Users gehört (z. B. Giro -> Tagesgeld). Umbuchungen sind
keine Einnahmen/Ausgaben und werden aus allen Einnahmen-/Ausgaben-Statistiken
ausgeschlossen (Filter `is_transfer == False`, analog zu `is_split_parent`).

User-scoped: nur eigene Konten/Transaktionen; Konten anderer User (auch im
selben Haushalt) zählen NICHT als Umbuchungsziel — Geld an die Partnerin ist
eine echte Ausgabe.
"""

from sqlalchemy.orm import Session

from ..models import Account, Transaction


def _normalize_iban(iban: str) -> str:
    return (iban or "").replace(" ", "").upper()


def detect_transfers_for_user(db: Session, user_id: int) -> int:
    """Markiert bisher unmarkierte Umbuchungen des Users. Returns count.

    Setzt nur is_transfer=True (nie zurück) — eine manuelle Abwahl im
    Detail-Dialog wird beim nächsten Lauf also wieder gesetzt, solange die
    Gegenseiten-IBAN ein eigenes Konto bleibt.
    """
    accounts = db.query(Account).filter(Account.user_id == user_id).all()
    own_ibans = {_normalize_iban(a.iban) for a in accounts if a.iban}
    account_ids = [a.id for a in accounts]
    if not account_ids or not own_ibans:
        return 0

    candidates = db.query(Transaction).filter(
        Transaction.account_id.in_(account_ids),
        Transaction.is_transfer == False,
        Transaction.counterpart_iban != None,
        Transaction.counterpart_iban != "",
    ).all()

    count = 0
    for tx in candidates:
        if _normalize_iban(tx.counterpart_iban) in own_ibans:
            tx.is_transfer = True
            count += 1

    db.commit()
    return count
