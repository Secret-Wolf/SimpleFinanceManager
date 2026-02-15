from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import date, timedelta
from typing import Optional
from calendar import monthrange
from dateutil.relativedelta import relativedelta

from ..database import get_db
from ..models import Transaction, Category, Account
from ..services.statistics import (
    get_dashboard_summary,
    get_stats_by_category,
    get_stats_over_time,
    get_shared_summary
)
from .. import schemas

router = APIRouter(prefix="/api/stats", tags=["statistics"])


def find_last_salary_date(db: Session) -> Optional[date]:
    """
    Find the date of the last salary payment.
    First checks by category name 'Gehalt', then falls back to keyword search.
    """
    import re

    # First, try to find by category name "Gehalt" (most reliable)
    salary_by_category = db.query(Transaction).join(
        Category, Transaction.category_id == Category.id
    ).filter(
        Transaction.amount > 0,
        Transaction.is_split_parent == False,
        Category.name == 'Gehalt'
    ).order_by(desc(Transaction.booking_date)).first()

    if salary_by_category:
        return salary_by_category.booking_date

    # Fallback: search by keywords in text
    salary_keywords = ['gehalt', 'lohn', 'salary', 'bezüge', 'bezuege', 'entgelt', 'arbeitsentgelt']
    exclude_keywords = ['kindergeld', 'elterngeld', 'wohngeld', 'bürgergeld', 'buergergeld', 'pflegegeld']

    recent_income = db.query(Transaction).filter(
        Transaction.amount > 0,
        Transaction.is_split_parent == False
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
    db: Session = Depends(get_db)
):
    """Get dashboard summary data"""
    return get_dashboard_summary(db, account_id=account_id, profile_id=profile_id)


@router.get("/by-category", response_model=schemas.StatsByCategory)
def get_by_category(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("month", regex="^(week|month|last_month|quarter|year|since_salary|custom)$"),
    account_id: Optional[int] = None,
    profile_id: Optional[int] = None,
    shared_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get statistics grouped by category"""

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
        # Go back to first day of last month
        last_month = today - relativedelta(months=1)
        start_date = date(last_month.year, last_month.month, 1)
        # Last day of last month
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
        salary_date = find_last_salary_date(db)
        if salary_date:
            start_date = salary_date
            end_date = today
        else:
            # Fallback to current month if no salary found
            start_date = date(today.year, today.month, 1)
            end_date = today
    else:
        start_date = date(today.year, today.month, 1)
        end_date = today

    return get_stats_by_category(db, start_date, end_date, account_id=account_id, profile_id=profile_id, shared_only=shared_only)


@router.get("/over-time", response_model=schemas.StatsOverTime)
def get_over_time(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("year", regex="^(month|last_month|quarter|year|since_salary|custom)$"),
    group_by: str = Query("month", regex="^(day|week|month)$"),
    account_id: Optional[int] = None,
    profile_id: Optional[int] = None,
    shared_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get income/expenses over time"""

    today = date.today()

    if period == "custom" and start_date and end_date:
        # Keep group_by as provided or default to day for short periods
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
        salary_date = find_last_salary_date(db)
        if salary_date:
            start_date = salary_date
            end_date = today
            # Choose group_by based on time span
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

    return get_stats_over_time(db, start_date, end_date, group_by, account_id=account_id, profile_id=profile_id, shared_only=shared_only)


@router.get("/shared-summary", response_model=schemas.SharedSummary)
def get_shared_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("month", regex="^(week|month|last_month|quarter|year|since_salary|custom)$"),
    db: Session = Depends(get_db)
):
    """Get shared expenses summary across all profiles"""
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
        salary_date = find_last_salary_date(db)
        if salary_date:
            start_date = salary_date
            end_date = today
        else:
            start_date = date(today.year, today.month, 1)
            end_date = today
    else:
        start_date = date(today.year, today.month, 1)
        end_date = today

    return get_shared_summary(db, start_date, end_date)


@router.get("/last-salary-date")
def get_last_salary_date(db: Session = Depends(get_db)):
    """Get the date of the last salary payment"""
    salary_date = find_last_salary_date(db)
    return {"date": salary_date.isoformat() if salary_date else None}
