from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, extract
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional
from calendar import monthrange

from ..models import Transaction, Category, Account, Profile
from .. import schemas


def _get_profile_account_ids(db: Session, profile_id: int) -> List[int]:
    """Get account IDs belonging to a profile"""
    return [a.id for a in db.query(Account.id).filter(Account.profile_id == profile_id).all()]


def _apply_filters(query, account_id=None, profile_id=None, shared_only=False, db=None):
    """Apply common filters to a transaction query"""
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    elif profile_id and db:
        account_ids = _get_profile_account_ids(db, profile_id)
        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))
        else:
            query = query.filter(Transaction.id == -1)
    if shared_only:
        query = query.filter(Transaction.is_shared == True)
    return query


def get_current_balance(db: Session, account_id: int = None, account_iban: str = None, profile_id: int = None) -> Optional[Decimal]:
    """Get balance from most recent transaction"""
    if profile_id:
        # Sum balances across all profile accounts
        account_ids = _get_profile_account_ids(db, profile_id)
        if not account_ids:
            return None
        total = Decimal("0")
        for aid in account_ids:
            latest = db.query(Transaction).filter(
                Transaction.balance_after != None,
                Transaction.is_split_parent == False,
                Transaction.account_id == aid
            ).order_by(Transaction.booking_date.desc(), Transaction.id.desc()).first()
            if latest and latest.balance_after:
                total += latest.balance_after
        return total if total != Decimal("0") else None

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
    account_iban: str = None,
    profile_id: int = None,
    shared_only: bool = False
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
    elif profile_id:
        account_ids = _get_profile_account_ids(db, profile_id)
        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))
        else:
            return {"income": Decimal("0"), "expenses": Decimal("0")}

    if shared_only:
        query = query.filter(Transaction.is_shared == True)

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
    account_id: int = None,
    profile_id: int = None
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
    elif profile_id:
        account_ids = _get_profile_account_ids(db, profile_id)
        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))

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


def get_uncategorized_count(db: Session, account_id: int = None, profile_id: int = None) -> int:
    """Count transactions without category"""
    query = db.query(Transaction).filter(
        Transaction.category_id == None,
        Transaction.is_split_parent == False
    )
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    elif profile_id:
        account_ids = _get_profile_account_ids(db, profile_id)
        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))
    return query.count()


def get_recent_transactions(db: Session, limit: int = 10, account_id: int = None, profile_id: int = None) -> List[Transaction]:
    """Get most recent transactions"""
    query = db.query(Transaction).filter(
        Transaction.is_split_parent == False
    )
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    elif profile_id:
        account_ids = _get_profile_account_ids(db, profile_id)
        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))
    return query.order_by(
        Transaction.booking_date.desc(),
        Transaction.id.desc()
    ).limit(limit).all()


def get_shared_expenses_current_month(db: Session) -> Decimal:
    """Get total shared expenses for current month"""
    today = date.today()
    first_of_month = date(today.year, today.month, 1)

    result = db.query(func.sum(Transaction.amount)).filter(
        Transaction.is_shared == True,
        Transaction.amount < 0,
        Transaction.booking_date >= first_of_month,
        Transaction.booking_date <= today,
        Transaction.is_split_parent == False
    ).scalar()

    return abs(result) if result else Decimal("0")


def get_dashboard_summary(db: Session, account_id: int = None, profile_id: int = None) -> schemas.DashboardSummary:
    """Get all dashboard data"""
    today = date.today()

    # Current month
    current_start, current_end = get_month_range(today.year, today.month)
    current_totals = get_period_totals(db, current_start, current_end, account_id=account_id, profile_id=profile_id)

    # Previous month
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1

    prev_start, prev_end = get_month_range(prev_year, prev_month)
    prev_totals = get_period_totals(db, prev_start, prev_end, account_id=account_id, profile_id=profile_id)

    # Top categories for current month
    top_cats = get_top_categories(db, current_start, current_end, account_id=account_id, profile_id=profile_id)

    # Recent transactions
    recent = get_recent_transactions(db, account_id=account_id, profile_id=profile_id)

    return schemas.DashboardSummary(
        current_balance=get_current_balance(db, account_id=account_id, profile_id=profile_id),
        income_current_month=current_totals["income"],
        expenses_current_month=current_totals["expenses"],
        income_previous_month=prev_totals["income"],
        expenses_previous_month=prev_totals["expenses"],
        shared_expenses_current_month=get_shared_expenses_current_month(db),
        uncategorized_count=get_uncategorized_count(db, account_id=account_id, profile_id=profile_id),
        top_categories=top_cats,
        recent_transactions=recent
    )


def get_stats_by_category(
    db: Session,
    start_date: date,
    end_date: date,
    include_income: bool = False,
    account_id: int = None,
    profile_id: int = None,
    shared_only: bool = False
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
    elif profile_id:
        account_ids = _get_profile_account_ids(db, profile_id)
        if account_ids:
            join_conditions.append(Transaction.account_id.in_(account_ids))
    if shared_only:
        join_conditions.append(Transaction.is_shared == True)

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
    elif profile_id:
        account_ids = _get_profile_account_ids(db, profile_id)
        if account_ids:
            uncat_query = uncat_query.filter(Transaction.account_id.in_(account_ids))
    if shared_only:
        uncat_query = uncat_query.filter(Transaction.is_shared == True)
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
    account_id: int = None,
    profile_id: int = None,
    shared_only: bool = False
) -> schemas.StatsOverTime:
    """Get income/expenses over time"""

    query = db.query(Transaction).filter(
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False
    )
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    elif profile_id:
        account_ids = _get_profile_account_ids(db, profile_id)
        if account_ids:
            query = query.filter(Transaction.account_id.in_(account_ids))
    if shared_only:
        query = query.filter(Transaction.is_shared == True)
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


def get_shared_summary(
    db: Session,
    start_date: date,
    end_date: date
) -> schemas.SharedSummary:
    """Get shared expenses summary across all profiles"""

    # Get all shared expense transactions in period
    shared_txs = db.query(Transaction).filter(
        Transaction.is_shared == True,
        Transaction.amount < 0,
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False
    ).all()

    total_shared = Decimal("0")
    profile_totals = {}  # profile_id -> total paid

    for tx in shared_txs:
        amount = abs(tx.amount)
        total_shared += amount

        # Find profile via account
        if tx.account_id:
            account = db.query(Account).filter(Account.id == tx.account_id).first()
            pid = account.profile_id if account else None
        else:
            pid = None

        if pid not in profile_totals:
            profile_totals[pid] = Decimal("0")
        profile_totals[pid] += amount

    # Build profile expenses list
    profiles = db.query(Profile).all()
    profile_map = {p.id: p for p in profiles}

    by_profile = []
    for pid, total_paid in profile_totals.items():
        if pid and pid in profile_map:
            p = profile_map[pid]
            by_profile.append(schemas.ProfileExpenses(
                profile_id=p.id,
                profile_name=p.name,
                profile_color=p.color,
                total_paid=total_paid
            ))
        else:
            by_profile.append(schemas.ProfileExpenses(
                profile_id=0,
                profile_name="Nicht zugeordnet",
                profile_color="#888888",
                total_paid=total_paid
            ))

    by_profile.sort(key=lambda x: x.total_paid, reverse=True)

    # Get category breakdown for shared expenses
    months = max(1, (end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1)

    cat_query = db.query(
        Category.id,
        Category.name,
        Category.color,
        func.sum(Transaction.amount).label("total"),
        func.count(Transaction.id).label("count")
    ).join(
        Transaction, Transaction.category_id == Category.id
    ).filter(
        Transaction.is_shared == True,
        Transaction.amount < 0,
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False
    ).group_by(Category.id).order_by(func.sum(Transaction.amount).asc()).all()

    by_category = [
        schemas.CategoryStats(
            category_id=r.id,
            category_name=r.name,
            category_color=r.color,
            total=abs(r.total) if r.total else Decimal("0"),
            average_monthly=abs(r.total) / months if r.total else Decimal("0"),
            transaction_count=r.count or 0
        )
        for r in cat_query
    ]

    return schemas.SharedSummary(
        total_shared_expenses=total_shared,
        by_profile=by_profile,
        by_category=by_category
    )
