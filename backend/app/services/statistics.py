from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, extract
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional
from calendar import monthrange

from ..models import Transaction, Category
from .. import schemas


def get_current_balance(db: Session, account_id: int = None, account_iban: str = None) -> Optional[Decimal]:
    """Get balance from most recent transaction"""
    query = db.query(Transaction).filter(
        Transaction.balance_after != None,
        Transaction.is_split_parent == False
    )

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    elif account_iban:
        query = query.filter(Transaction.account_iban == account_iban)

    latest = query.order_by(Transaction.booking_date.desc(), Transaction.id.desc()).first()

    return latest.balance_after if latest else None


def get_period_totals(
    db: Session,
    start_date: date,
    end_date: date,
    account_id: int = None,
    account_iban: str = None
) -> Dict[str, Decimal]:
    """Get income and expenses for a period"""

    query = db.query(Transaction).filter(
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False
    )

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    elif account_iban:
        query = query.filter(Transaction.account_iban == account_iban)

    transactions = query.all()

    income = Decimal("0")
    expenses = Decimal("0")

    for t in transactions:
        if t.amount > 0:
            income += t.amount
        else:
            expenses += abs(t.amount)

    return {"income": income, "expenses": expenses}


def get_month_range(year: int, month: int) -> tuple:
    """Get start and end date for a month"""
    start = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end = date(year, month, last_day)
    return start, end


def get_top_categories(
    db: Session,
    start_date: date,
    end_date: date,
    limit: int = 5,
    expenses_only: bool = True,
    account_id: int = None
) -> List[Dict]:
    """Get top spending categories"""

    query = db.query(
        Category.id,
        Category.name,
        Category.color,
        func.sum(Transaction.amount).label("total")
    ).join(
        Transaction, Transaction.category_id == Category.id
    ).filter(
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False
    )

    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    if expenses_only:
        query = query.filter(Transaction.amount < 0)

    results = query.group_by(Category.id).order_by(
        func.sum(Transaction.amount).asc()  # Most negative first for expenses
    ).limit(limit).all()

    return [
        {
            "category_id": r.id,
            "category_name": r.name,
            "category_color": r.color,
            "total": abs(r.total) if r.total else Decimal("0")
        }
        for r in results
    ]


def get_uncategorized_count(db: Session, account_id: int = None) -> int:
    """Count transactions without category"""
    query = db.query(Transaction).filter(
        Transaction.category_id == None,
        Transaction.is_split_parent == False
    )
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    return query.count()


def get_recent_transactions(db: Session, limit: int = 10, account_id: int = None) -> List[Transaction]:
    """Get most recent transactions"""
    query = db.query(Transaction).filter(
        Transaction.is_split_parent == False
    )
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    return query.order_by(
        Transaction.booking_date.desc(),
        Transaction.id.desc()
    ).limit(limit).all()


def get_dashboard_summary(db: Session, account_id: int = None) -> schemas.DashboardSummary:
    """Get all dashboard data"""
    today = date.today()

    # Current month
    current_start, current_end = get_month_range(today.year, today.month)
    current_totals = get_period_totals(db, current_start, current_end, account_id=account_id)

    # Previous month
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1

    prev_start, prev_end = get_month_range(prev_year, prev_month)
    prev_totals = get_period_totals(db, prev_start, prev_end, account_id=account_id)

    # Top categories for current month
    top_cats = get_top_categories(db, current_start, current_end, account_id=account_id)

    # Recent transactions
    recent = get_recent_transactions(db, account_id=account_id)

    return schemas.DashboardSummary(
        current_balance=get_current_balance(db, account_id=account_id),
        income_current_month=current_totals["income"],
        expenses_current_month=current_totals["expenses"],
        income_previous_month=prev_totals["income"],
        expenses_previous_month=prev_totals["expenses"],
        uncategorized_count=get_uncategorized_count(db, account_id=account_id),
        top_categories=top_cats,
        recent_transactions=recent
    )


def get_stats_by_category(
    db: Session,
    start_date: date,
    end_date: date,
    include_income: bool = False,
    account_id: int = None
) -> schemas.StatsByCategory:
    """Get statistics grouped by category"""

    # Calculate months in period for average
    months = max(1, (end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1)

    # Build join conditions
    join_conditions = [
        Transaction.category_id == Category.id,
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False
    ]
    if account_id:
        join_conditions.append(Transaction.account_id == account_id)

    query = db.query(
        Category.id,
        Category.name,
        Category.color,
        Category.parent_id,
        func.sum(Transaction.amount).label("total"),
        func.count(Transaction.id).label("count")
    ).outerjoin(
        Transaction,
        and_(*join_conditions)
    ).group_by(Category.id).all()

    # Build category stats
    categories = []
    total_income = Decimal("0")
    total_expenses = Decimal("0")

    for r in query:
        total = r.total or Decimal("0")

        if total > 0:
            total_income += total
        else:
            total_expenses += abs(total)

        categories.append(schemas.CategoryStats(
            category_id=r.id,
            category_name=r.name,
            category_color=r.color,
            total=abs(total),
            average_monthly=abs(total) / months,
            transaction_count=r.count or 0
        ))

    # Add uncategorized
    uncat_query = db.query(
        func.sum(Transaction.amount).label("total"),
        func.count(Transaction.id).label("count")
    ).filter(
        Transaction.category_id == None,
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False
    )
    if account_id:
        uncat_query = uncat_query.filter(Transaction.account_id == account_id)
    uncategorized = uncat_query.first()

    if uncategorized.count and uncategorized.count > 0:
        total = uncategorized.total or Decimal("0")
        categories.append(schemas.CategoryStats(
            category_id=None,
            category_name="Unkategorisiert",
            category_color="#888888",
            total=abs(total),
            average_monthly=abs(total) / months,
            transaction_count=uncategorized.count
        ))

        if total > 0:
            total_income += total
        else:
            total_expenses += abs(total)

    # Sort by total descending
    categories.sort(key=lambda x: x.total, reverse=True)

    return schemas.StatsByCategory(
        categories=categories,
        total_income=total_income,
        total_expenses=total_expenses
    )


def get_stats_over_time(
    db: Session,
    start_date: date,
    end_date: date,
    group_by: str = "month",  # "day", "week", "month"
    account_id: int = None
) -> schemas.StatsOverTime:
    """Get income/expenses over time"""

    query = db.query(Transaction).filter(
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False
    )
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    transactions = query.order_by(Transaction.booking_date).all()

    # Group by period
    periods = {}

    for t in transactions:
        if group_by == "day":
            key = t.booking_date.strftime("%Y-%m-%d")
        elif group_by == "week":
            # ISO week
            key = t.booking_date.strftime("%Y-W%W")
        else:  # month
            key = t.booking_date.strftime("%Y-%m")

        if key not in periods:
            periods[key] = {"income": Decimal("0"), "expenses": Decimal("0")}

        if t.amount > 0:
            periods[key]["income"] += t.amount
        else:
            periods[key]["expenses"] += abs(t.amount)

    # Convert to list
    data = [
        schemas.TimeSeriesPoint(
            date=k,
            income=v["income"],
            expenses=v["expenses"]
        )
        for k, v in sorted(periods.items())
    ]

    total_income = sum(p.income for p in data)
    total_expenses = sum(p.expenses for p in data)

    return schemas.StatsOverTime(
        data=data,
        total_income=total_income,
        total_expenses=total_expenses
    )
