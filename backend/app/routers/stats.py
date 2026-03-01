from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import date, timedelta
from typing import Optional, List
from calendar import monthrange
from dateutil.relativedelta import relativedelta

from ..database import get_db
from ..auth import get_current_user
from ..models import Transaction, Category, Account, User
from ..services.statistics import (
    get_dashboard_summary,
    get_stats_by_category,
    get_stats_over_time,
    get_shared_summary
)
from .. import schemas

router = APIRouter(prefix="/api/stats", tags=["statistics"])


def _get_user_account_ids(db: Session, user: User) -> List[int]:
    """Get all account IDs owned by user"""
    return [a.id for a in db.query(Account.id).filter(Account.user_id == user.id).all()]


def _verify_account_ownership(account_id: int, user: User, db: Session):
    """Raise 403 if account_id does not belong to current user"""
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user.id
    ).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert"
        )


def find_last_salary_date(db: Session, user_account_ids: List[int]) -> Optional[date]:
    """
    Find the date of the last salary payment.
    First checks by category name 'Gehalt', then falls back to keyword search.
    """
    import re

    # First, try to find by category name "Gehalt" (most reliable)
    query = db.query(Transaction).join(
        Category, Transaction.category_id == Category.id
    ).filter(
        Transaction.amount > 0,
        Transaction.is_split_parent == False,
        Category.name == 'Gehalt',
        Transaction.account_id.in_(user_account_ids)
    ).order_by(desc(Transaction.booking_date))

    salary_by_category = query.first()

    if salary_by_category:
        return salary_by_category.booking_date

    # Fallback: search by keywords in text
    salary_keywords = ['gehalt', 'lohn', 'salary', 'bezüge', 'bezuege', 'entgelt', 'arbeitsentgelt']
    exclude_keywords = ['kindergeld', 'elterngeld', 'wohngeld', 'bürgergeld', 'buergergeld', 'pflegegeld']

    recent_income = db.query(Transaction).filter(
        Transaction.amount > 0,
        Transaction.is_split_parent == False,
        Transaction.account_id.in_(user_account_ids)
    ).order_by(desc(Transaction.booking_date)).limit(500).all()

    for tx in recent_income:
        text_to_search = f"{tx.purpose or ''} {tx.counterpart_name or ''}".lower()

        is_excluded = any(exclude in text_to_search for exclude in exclude_keywords)
        if is_excluded:
            continue

        for keyword in salary_keywords:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text_to_search):
                return tx.booking_date

    return None


@router.get("/summary", response_model=schemas.DashboardSummary)
def get_summary(
    account_id: Optional[int] = None,
    profile_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get dashboard summary data"""
    user_account_ids = _get_user_account_ids(db, current_user)

    if account_id:
        _verify_account_ownership(account_id, current_user, db)

    return get_dashboard_summary(
        db, account_id=account_id, profile_id=profile_id,
        user_account_ids=user_account_ids
    )


@router.get("/by-category", response_model=schemas.StatsByCategory)
def get_by_category(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("month", pattern="^(week|month|last_month|quarter|year|since_salary|custom)$"),
    account_id: Optional[int] = None,
    profile_id: Optional[int] = None,
    shared_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get statistics grouped by category"""
    user_account_ids = _get_user_account_ids(db, current_user)

    if account_id:
        _verify_account_ownership(account_id, current_user, db)

    today = date.today()

    if period == "custom" and start_date and end_date:
        pass
    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif period == "month":
        start_date = date(today.year, today.month, 1)
        end_date = today
    elif period == "last_month":
        last_month = today - relativedelta(months=1)
        start_date = date(last_month.year, last_month.month, 1)
        _, last_day = monthrange(last_month.year, last_month.month)
        end_date = date(last_month.year, last_month.month, last_day)
    elif period == "quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start_date = date(today.year, quarter_month, 1)
        end_date = today
    elif period == "year":
        start_date = date(today.year, 1, 1)
        end_date = today
    elif period == "since_salary":
        salary_date = find_last_salary_date(db, user_account_ids)
        if salary_date:
            start_date = salary_date
            end_date = today
        else:
            start_date = date(today.year, today.month, 1)
            end_date = today
    else:
        start_date = date(today.year, today.month, 1)
        end_date = today

    return get_stats_by_category(
        db, start_date, end_date,
        account_id=account_id, profile_id=profile_id,
        shared_only=shared_only, user_account_ids=user_account_ids
    )


@router.get("/over-time", response_model=schemas.StatsOverTime)
def get_over_time(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("year", pattern="^(month|last_month|quarter|year|since_salary|custom)$"),
    group_by: str = Query("month", pattern="^(day|week|month)$"),
    account_id: Optional[int] = None,
    profile_id: Optional[int] = None,
    shared_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get income/expenses over time"""
    user_account_ids = _get_user_account_ids(db, current_user)

    if account_id:
        _verify_account_ownership(account_id, current_user, db)

    today = date.today()

    if period == "custom" and start_date and end_date:
        days_diff = (end_date - start_date).days
        if days_diff <= 31:
            group_by = "day"
        elif days_diff <= 120:
            group_by = "week"
        else:
            group_by = "month"
    elif period == "month":
        start_date = date(today.year, today.month, 1)
        end_date = today
        group_by = "day"
    elif period == "last_month":
        last_month = today - relativedelta(months=1)
        start_date = date(last_month.year, last_month.month, 1)
        _, last_day = monthrange(last_month.year, last_month.month)
        end_date = date(last_month.year, last_month.month, last_day)
        group_by = "day"
    elif period == "quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start_date = date(today.year, quarter_month, 1)
        end_date = today
        group_by = "week"
    elif period == "year":
        start_date = date(today.year, 1, 1)
        end_date = today
        group_by = "month"
    elif period == "since_salary":
        salary_date = find_last_salary_date(db, user_account_ids)
        if salary_date:
            start_date = salary_date
            end_date = today
            days_diff = (end_date - start_date).days
            if days_diff <= 31:
                group_by = "day"
            elif days_diff <= 120:
                group_by = "week"
            else:
                group_by = "month"
        else:
            start_date = date(today.year, today.month, 1)
            end_date = today
            group_by = "day"
    else:
        start_date = date(today.year, 1, 1)
        end_date = today

    return get_stats_over_time(
        db, start_date, end_date, group_by,
        account_id=account_id, profile_id=profile_id,
        shared_only=shared_only, user_account_ids=user_account_ids
    )


@router.get("/shared-summary", response_model=schemas.SharedSummary)
def get_shared_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("month", pattern="^(week|month|last_month|quarter|year|since_salary|custom)$"),
    household_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get shared expenses summary across household members"""
    user_account_ids = _get_user_account_ids(db, current_user)

    today = date.today()

    if period == "custom" and start_date and end_date:
        pass
    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif period == "month":
        start_date = date(today.year, today.month, 1)
        end_date = today
    elif period == "last_month":
        last_month = today - relativedelta(months=1)
        start_date = date(last_month.year, last_month.month, 1)
        _, last_day = monthrange(last_month.year, last_month.month)
        end_date = date(last_month.year, last_month.month, last_day)
    elif period == "quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start_date = date(today.year, quarter_month, 1)
        end_date = today
    elif period == "year":
        start_date = date(today.year, 1, 1)
        end_date = today
    elif period == "since_salary":
        salary_date = find_last_salary_date(db, user_account_ids)
        if salary_date:
            start_date = salary_date
            end_date = today
        else:
            start_date = date(today.year, today.month, 1)
            end_date = today
    else:
        start_date = date(today.year, today.month, 1)
        end_date = today

    # Determine which accounts to include in shared summary
    household_account_ids = None
    if household_id:
        # Get all accounts from all household members
        from ..models import HouseholdMember
        member_user_ids = [m.user_id for m in db.query(HouseholdMember.user_id).filter(
            HouseholdMember.household_id == household_id
        ).all()]
        # Verify current user is a member
        if current_user.id not in member_user_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Zugriff verweigert"
            )
        household_account_ids = [a.id for a in db.query(Account.id).filter(
            Account.user_id.in_(member_user_ids)
        ).all()]
    else:
        # Default: only own accounts
        household_account_ids = user_account_ids

    return get_shared_summary(db, start_date, end_date, household_account_ids=household_account_ids)


@router.get("/last-salary-date")
def get_last_salary_date(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get the date of the last salary payment"""
    user_account_ids = _get_user_account_ids(db, current_user)
    salary_date = find_last_salary_date(db, user_account_ids)
    return {"date": salary_date.isoformat() if salary_date else None}
