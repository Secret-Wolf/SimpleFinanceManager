from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import List, Optional
from decimal import Decimal

from ..database import get_db
from ..models import Account, Transaction
from .. import schemas

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=List[schemas.Account])
def get_accounts(
    include_inactive: bool = False,
    profile_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all accounts, optionally filtered by profile"""
    query = db.query(Account)

    if not include_inactive:
        query = query.filter(Account.is_active == True)

    if profile_id:
        query = query.filter(Account.profile_id == profile_id)

    accounts = query.order_by(Account.name).all()
    return accounts


@router.get("/summary")
def get_accounts_summary(
    profile_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get summary of all active accounts with balances"""
    query = db.query(Account).filter(Account.is_active == True)
    if profile_id:
        query = query.filter(Account.profile_id == profile_id)
    accounts = query.all()

    result = []
    total_balance = Decimal("0")

    for account in accounts:
        # Get latest balance from most recent transaction
        latest_tx = db.query(Transaction).filter(
            Transaction.account_id == account.id,
            Transaction.balance_after.isnot(None)
        ).order_by(Transaction.booking_date.desc(), Transaction.id.desc()).first()

        balance = latest_tx.balance_after if latest_tx else None

        # Get transaction count
        tx_count = db.query(func.count(Transaction.id)).filter(
            Transaction.account_id == account.id
        ).scalar()

        # Get income/expenses this month
        from datetime import date
        today = date.today()
        first_of_month = today.replace(day=1)

        monthly_stats = db.query(
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label('income'),
            func.sum(case((Transaction.amount < 0, Transaction.amount), else_=0)).label('expenses')
        ).filter(
            Transaction.account_id == account.id,
            Transaction.booking_date >= first_of_month
        ).first()

        if balance:
            total_balance += balance

        result.append({
            "id": account.id,
            "name": account.name,
            "iban": account.iban,
            "bank_name": account.bank_name,
            "account_type": account.account_type,
            "profile_id": account.profile_id,
            "balance": balance,
            "transaction_count": tx_count,
            "income_this_month": monthly_stats.income or Decimal("0"),
            "expenses_this_month": monthly_stats.expenses or Decimal("0")
        })

    return {
        "accounts": result,
        "total_balance": total_balance,
        "account_count": len(result)
    }


@router.get("/{account_id}")
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get single account with details"""
    account = db.query(Account).filter(Account.id == account_id).first()

    if not account:
        raise HTTPException(status_code=404, detail="Konto nicht gefunden")

    # Get latest balance
    latest_tx = db.query(Transaction).filter(
        Transaction.account_id == account.id,
        Transaction.balance_after.isnot(None)
    ).order_by(Transaction.booking_date.desc(), Transaction.id.desc()).first()

    # Get transaction count
    tx_count = db.query(func.count(Transaction.id)).filter(
        Transaction.account_id == account.id
    ).scalar()

    # Get date range
    date_range = db.query(
        func.min(Transaction.booking_date).label('first'),
        func.max(Transaction.booking_date).label('last')
    ).filter(Transaction.account_id == account.id).first()

    return {
        "id": account.id,
        "name": account.name,
        "iban": account.iban,
        "bic": account.bic,
        "bank_name": account.bank_name,
        "account_type": account.account_type,
        "is_active": account.is_active,
        "profile_id": account.profile_id,
        "created_at": account.created_at,
        "balance": latest_tx.balance_after if latest_tx else None,
        "transaction_count": tx_count,
        "first_transaction": date_range.first if date_range else None,
        "last_transaction": date_range.last if date_range else None
    }


@router.patch("/{account_id}")
def update_account(
    account_id: int,
    name: str = None,
    is_active: bool = None,
    profile_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Update account (name, active status, profile assignment)"""
    account = db.query(Account).filter(Account.id == account_id).first()

    if not account:
        raise HTTPException(status_code=404, detail="Konto nicht gefunden")

    if name is not None:
        account.name = name

    if is_active is not None:
        account.is_active = is_active

    if profile_id is not None:
        from ..models import Profile
        if profile_id == 0:
            account.profile_id = None
        else:
            profile = db.query(Profile).filter(Profile.id == profile_id).first()
            if not profile:
                raise HTTPException(status_code=400, detail="Profil nicht gefunden")
            account.profile_id = profile_id

    db.commit()
    db.refresh(account)

    return {"status": "success", "account": account}
