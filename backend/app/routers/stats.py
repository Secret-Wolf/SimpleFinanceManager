from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date, timedelta
from typing import Optional

from ..database import get_db
from ..services.statistics import (
    get_dashboard_summary,
    get_stats_by_category,
    get_stats_over_time
)
from .. import schemas

router = APIRouter(prefix="/api/stats", tags=["statistics"])


@router.get("/summary", response_model=schemas.DashboardSummary)
def get_summary(db: Session = Depends(get_db)):
    """Get dashboard summary data"""
    return get_dashboard_summary(db)


@router.get("/by-category", response_model=schemas.StatsByCategory)
def get_by_category(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("month", regex="^(week|month|quarter|year|custom)$"),
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
    elif period == "quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start_date = date(today.year, quarter_month, 1)
        end_date = today
    elif period == "year":
        start_date = date(today.year, 1, 1)
        end_date = today
    else:
        start_date = date(today.year, today.month, 1)
        end_date = today

    return get_stats_by_category(db, start_date, end_date)


@router.get("/over-time", response_model=schemas.StatsOverTime)
def get_over_time(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = Query("year", regex="^(month|quarter|year|custom)$"),
    group_by: str = Query("month", regex="^(day|week|month)$"),
    db: Session = Depends(get_db)
):
    """Get income/expenses over time"""

    today = date.today()

    if period == "custom" and start_date and end_date:
        pass
    elif period == "month":
        start_date = date(today.year, today.month, 1)
        end_date = today
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
    else:
        start_date = date(today.year, 1, 1)
        end_date = today

    return get_stats_over_time(db, start_date, end_date, group_by)
