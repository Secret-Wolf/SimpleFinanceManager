from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from .. import schemas
from ..models import Account, Category, Transaction


def _apply_user_scope(query, user_account_ids: List[int] = None):
    """Apply base user scope to a transaction query"""
    if user_account_ids is not None:
        query = query.filter(Transaction.account_id.in_(user_account_ids))
    return query


def get_current_balance(
    db: Session,
    account_id: int = None,
    user_account_ids: List[int] = None
) -> Optional[Decimal]:
    """Get balance from most recent transaction"""
    query = db.query(Transaction).filter(
        Transaction.balance_after != None,
        Transaction.is_split_parent == False
    )
    query = _apply_user_scope(query, user_account_ids)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    latest = query.order_by(Transaction.booking_date.desc(), Transaction.id.desc()).first()

    return latest.balance_after if latest else None


def get_period_totals(
    db: Session,
    start_date: date,
    end_date: date,
    account_id: int = None,
    shared_only: bool = False,
    user_account_ids: List[int] = None
) -> Dict[str, Decimal]:
    """Get income and expenses for a period"""

    query = db.query(Transaction).filter(
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    )
    query = _apply_user_scope(query, user_account_ids)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)

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
    user_account_ids: List[int] = None
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
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    )

    if user_account_ids is not None:
        query = query.filter(Transaction.account_id.in_(user_account_ids))

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


def get_uncategorized_count(
    db: Session,
    account_id: int = None,
    user_account_ids: List[int] = None
) -> int:
    """Count transactions without category (Umbuchungen brauchen keine)"""
    query = db.query(Transaction).filter(
        Transaction.category_id == None,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    )
    query = _apply_user_scope(query, user_account_ids)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    return query.count()


def get_recent_transactions(
    db: Session,
    limit: int = 10,
    account_id: int = None,
    user_account_ids: List[int] = None
) -> List[Transaction]:
    """Get most recent transactions"""
    query = db.query(Transaction).filter(
        Transaction.is_split_parent == False
    )
    query = _apply_user_scope(query, user_account_ids)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    return query.order_by(
        Transaction.booking_date.desc(),
        Transaction.id.desc()
    ).limit(limit).all()


def get_shared_expenses_current_month(db: Session, user_account_ids: List[int] = None) -> Decimal:
    """Get total shared expenses for current month"""
    today = date.today()
    first_of_month = date(today.year, today.month, 1)

    query = db.query(func.sum(Transaction.amount)).filter(
        Transaction.is_shared == True,
        Transaction.amount < 0,
        Transaction.booking_date >= first_of_month,
        Transaction.booking_date <= today,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    )
    if user_account_ids is not None:
        query = query.filter(Transaction.account_id.in_(user_account_ids))

    result = query.scalar()

    return abs(result) if result else Decimal("0")


def get_dashboard_summary(
    db: Session,
    account_id: int = None,
    user_account_ids: List[int] = None
) -> schemas.DashboardSummary:
    """Get all dashboard data"""
    today = date.today()

    # Current month
    current_start, current_end = get_month_range(today.year, today.month)
    current_totals = get_period_totals(
        db, current_start, current_end,
        account_id=account_id,
        user_account_ids=user_account_ids
    )

    # Previous month
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1

    prev_start, prev_end = get_month_range(prev_year, prev_month)
    prev_totals = get_period_totals(
        db, prev_start, prev_end,
        account_id=account_id,
        user_account_ids=user_account_ids
    )

    # Top categories for current month
    top_cats = get_top_categories(
        db, current_start, current_end,
        account_id=account_id,
        user_account_ids=user_account_ids
    )

    # Recent transactions
    recent = get_recent_transactions(
        db, account_id=account_id,
        user_account_ids=user_account_ids
    )

    return schemas.DashboardSummary(
        current_balance=get_current_balance(
            db, account_id=account_id,
            user_account_ids=user_account_ids
        ),
        income_current_month=current_totals["income"],
        expenses_current_month=current_totals["expenses"],
        income_previous_month=prev_totals["income"],
        expenses_previous_month=prev_totals["expenses"],
        shared_expenses_current_month=get_shared_expenses_current_month(
            db, user_account_ids=user_account_ids
        ),
        uncategorized_count=get_uncategorized_count(
            db, account_id=account_id,
            user_account_ids=user_account_ids
        ),
        top_categories=top_cats,
        recent_transactions=recent
    )


def get_stats_by_category(
    db: Session,
    start_date: date,
    end_date: date,
    include_income: bool = False,
    account_id: int = None,
    shared_only: bool = False,
    user_account_ids: List[int] = None,
    user_id: int = None
) -> schemas.StatsByCategory:
    """Get statistics grouped by category.

    Returns top-level categories with nested `children`; totals/counts are
    rolled up over the whole subtree (Teilbaum-Roll-up). total_income/
    total_expenses are computed from each category's own transactions, so
    nothing is double-counted."""

    # Calculate months in period for average
    months = max(1, (end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1)

    # Build join conditions
    join_conditions = [
        Transaction.category_id == Category.id,
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    ]
    if user_account_ids is not None:
        join_conditions.append(Transaction.account_id.in_(user_account_ids))
    if account_id:
        join_conditions.append(Transaction.account_id == account_id)
    if shared_only:
        join_conditions.append(Transaction.is_shared == True)

    cat_query = db.query(
        Category.id,
        Category.name,
        Category.color,
        Category.parent_id,
        func.sum(Transaction.amount).label("total"),
        func.count(Transaction.id).label("count")
    )
    if user_id is not None:
        cat_query = cat_query.filter(Category.user_id == user_id)
    query = cat_query.outerjoin(
        Transaction,
        and_(*join_conditions)
    ).group_by(Category.id).all()

    # Per-category raw values (signed), keyed by id
    nodes = {}
    total_income = Decimal("0")
    total_expenses = Decimal("0")

    for r in query:
        own_total = r.total or Decimal("0")

        if own_total > 0:
            total_income += own_total
        else:
            total_expenses += abs(own_total)

        nodes[r.id] = {
            "name": r.name,
            "color": r.color,
            "parent_id": r.parent_id,
            "own_total": own_total,
            "own_count": r.count or 0,
        }

    # Tree structure (orphaned parent_ids are treated as top-level)
    children_of = {}
    for cid, n in nodes.items():
        pid = n["parent_id"] if n["parent_id"] in nodes else None
        children_of.setdefault(pid, []).append(cid)

    def build_subtree(node_id):
        """Returns (CategoryStats with rolled-up totals, signed subtree total)."""
        node = nodes[node_id]
        child_stats = []
        signed_total = node["own_total"]
        count = node["own_count"]
        for child_id in children_of.get(node_id, []):
            stats, child_signed = build_subtree(child_id)
            child_stats.append(stats)
            signed_total += child_signed
            count += stats.transaction_count
        child_stats.sort(key=lambda x: x.total, reverse=True)
        return schemas.CategoryStats(
            category_id=node_id,
            category_name=node["name"],
            category_color=node["color"],
            total=abs(signed_total),
            average_monthly=abs(signed_total) / months,
            transaction_count=count,
            children=child_stats
        ), signed_total

    categories = [build_subtree(root_id)[0] for root_id in children_of.get(None, [])]

    # Add uncategorized
    uncat_query = db.query(
        func.sum(Transaction.amount).label("total"),
        func.count(Transaction.id).label("count")
    ).filter(
        Transaction.category_id == None,
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    )
    if user_account_ids is not None:
        uncat_query = uncat_query.filter(Transaction.account_id.in_(user_account_ids))
    if account_id:
        uncat_query = uncat_query.filter(Transaction.account_id == account_id)
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
    shared_only: bool = False,
    user_account_ids: List[int] = None
) -> schemas.StatsOverTime:
    """Get income/expenses over time"""

    query = db.query(Transaction).filter(
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    )
    query = _apply_user_scope(query, user_account_ids)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
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


def get_budget_stats_for_month(
    db: Session,
    user_id: int,
    year: int,
    month: int,
    start_date: date,
    end_date: date,
    user_account_ids: List[int] = None
) -> schemas.BudgetStatsList:
    """Budget vs. Ist je Kategorie mit Budget; 'Ist' = Ausgaben des Teilbaums.

    total_budget/total_spent zählen nur Budgets, die nicht innerhalb einer
    anderen budgetierten Kategorie liegen (sonst würde der Teilbaum doppelt zählen)."""

    cats = db.query(
        Category.id, Category.name, Category.color, Category.parent_id,
        Category.full_path, Category.budget_monthly
    ).filter(Category.user_id == user_id).all()

    # Ausgaben je Kategorie im Monat (eigene Transaktionen, ohne Splits/Umbuchungen)
    spent_query = db.query(
        Transaction.category_id,
        func.sum(Transaction.amount).label("total")
    ).filter(
        Transaction.amount < 0,
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False,
        Transaction.category_id != None
    )
    if user_account_ids is not None:
        spent_query = spent_query.filter(Transaction.account_id.in_(user_account_ids))
    own_spent = {r.category_id: abs(r.total or Decimal("0"))
                 for r in spent_query.group_by(Transaction.category_id).all()}

    children_of = {}
    parent_of = {}
    for c in cats:
        children_of.setdefault(c.parent_id, []).append(c.id)
        parent_of[c.id] = c.parent_id

    def subtree_spent(cat_id) -> Decimal:
        total = own_spent.get(cat_id, Decimal("0"))
        for child_id in children_of.get(cat_id, []):
            total += subtree_spent(child_id)
        return total

    budgeted = {c.id for c in cats if c.budget_monthly and c.budget_monthly > 0}

    def has_budgeted_ancestor(cat_id) -> bool:
        seen = {cat_id}
        parent = parent_of.get(cat_id)
        while parent is not None and parent not in seen:
            if parent in budgeted:
                return True
            seen.add(parent)
            parent = parent_of.get(parent)
        return False

    items = []
    total_budget = Decimal("0")
    total_spent = Decimal("0")

    for c in cats:
        if c.id not in budgeted:
            continue
        spent = subtree_spent(c.id)
        budget = c.budget_monthly
        percent = (spent / budget * 100).quantize(Decimal("0.1"))
        items.append(schemas.BudgetStats(
            category_id=c.id,
            category_name=c.name,
            category_color=c.color,
            full_path=c.full_path,
            budget=budget,
            spent=spent,
            remaining=budget - spent,
            percent=percent
        ))
        if not has_budgeted_ancestor(c.id):
            total_budget += budget
            total_spent += spent

    items.sort(key=lambda x: x.percent, reverse=True)

    return schemas.BudgetStatsList(
        year=year,
        month=month,
        items=items,
        total_budget=total_budget,
        total_spent=total_spent
    )


def get_shared_summary(
    db: Session,
    start_date: date,
    end_date: date,
    household_account_ids: List[int] = None
) -> schemas.SharedSummary:
    """Get shared expenses summary across household members"""

    query = db.query(Transaction).filter(
        Transaction.is_shared == True,
        Transaction.amount < 0,
        Transaction.booking_date >= start_date,
        Transaction.booking_date <= end_date,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    )
    if household_account_ids is not None:
        query = query.filter(Transaction.account_id.in_(household_account_ids))

    shared_txs = query.all()

    total_shared = Decimal("0")
    user_totals = {}  # user_id -> total paid

    for tx in shared_txs:
        amount = abs(tx.amount)
        total_shared += amount

        # Find user via account
        if tx.account_id:
            account = db.query(Account).filter(Account.id == tx.account_id).first()
            uid = account.user_id if account else None
        else:
            uid = None

        if uid not in user_totals:
            user_totals[uid] = Decimal("0")
        user_totals[uid] += amount

    # Build member expenses list using User model
    from ..models import User
    by_profile = []
    for uid, total_paid in user_totals.items():
        if uid:
            user = db.query(User).filter(User.id == uid).first()
            if user:
                by_profile.append(schemas.ProfileExpenses(
                    profile_id=user.id,
                    profile_name=user.display_name,
                    profile_color="#2563eb",
                    total_paid=total_paid
                ))
            else:
                by_profile.append(schemas.ProfileExpenses(
                    profile_id=0,
                    profile_name="Unbekannt",
                    profile_color="#888888",
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
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False
    )
    if household_account_ids is not None:
        cat_query = cat_query.filter(Transaction.account_id.in_(household_account_ids))

    cat_results = cat_query.group_by(Category.id).order_by(func.sum(Transaction.amount).asc()).all()

    by_category = [
        schemas.CategoryStats(
            category_id=r.id,
            category_name=r.name,
            category_color=r.color,
            total=abs(r.total) if r.total else Decimal("0"),
            average_monthly=abs(r.total) / months if r.total else Decimal("0"),
            transaction_count=r.count or 0
        )
        for r in cat_results
    ]

    return schemas.SharedSummary(
        total_shared_expenses=total_shared,
        by_profile=by_profile,
        by_category=by_category
    )
