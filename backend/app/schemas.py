from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List


# Category Schemas
class CategoryBase(BaseModel):
    name: str
    parent_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    budget_monthly: Optional[Decimal] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    budget_monthly: Optional[Decimal] = None


class Category(CategoryBase):
    id: int
    full_path: Optional[str] = None
    created_at: datetime
    transaction_count: Optional[int] = 0

    class Config:
        from_attributes = True


class CategoryTree(Category):
    children: List["CategoryTree"] = []


# Account Schemas
class AccountBase(BaseModel):
    name: str
    iban: str
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    account_type: Optional[str] = None


class AccountCreate(AccountBase):
    pass


class Account(AccountBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Transaction Schemas
class TransactionBase(BaseModel):
    booking_date: date
    value_date: Optional[date] = None
    counterpart_name: Optional[str] = None
    counterpart_iban: Optional[str] = None
    counterpart_bic: Optional[str] = None
    booking_type: Optional[str] = None
    purpose: Optional[str] = None
    amount: Decimal
    currency: str = "EUR"
    balance_after: Optional[Decimal] = None
    category_id: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None


class TransactionCreate(TransactionBase):
    account_iban: str


class TransactionUpdate(BaseModel):
    category_id: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None


class Transaction(TransactionBase):
    id: int
    import_hash: str
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    account_iban: Optional[str] = None
    bank_name: Optional[str] = None
    is_split_parent: bool = False
    parent_transaction_id: Optional[int] = None
    original_category: Optional[str] = None
    creditor_id: Optional[str] = None
    mandate_reference: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    category: Optional[Category] = None

    class Config:
        from_attributes = True


class TransactionList(BaseModel):
    items: List[Transaction]
    total: int
    page: int
    per_page: int
    pages: int


# Split Transaction
class SplitPart(BaseModel):
    amount: Decimal
    category_id: int
    notes: Optional[str] = None


class SplitTransactionCreate(BaseModel):
    parts: List[SplitPart]


# Rule Schemas
class RuleBase(BaseModel):
    name: Optional[str] = None
    priority: int = 0
    match_counterpart_name: Optional[str] = None
    match_counterpart_iban: Optional[str] = None
    match_purpose: Optional[str] = None
    match_booking_type: Optional[str] = None
    match_amount_min: Optional[Decimal] = None
    match_amount_max: Optional[Decimal] = None
    assign_category_id: int
    is_active: bool = True


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    priority: Optional[int] = None
    match_counterpart_name: Optional[str] = None
    match_counterpart_iban: Optional[str] = None
    match_purpose: Optional[str] = None
    match_booking_type: Optional[str] = None
    match_amount_min: Optional[Decimal] = None
    match_amount_max: Optional[Decimal] = None
    assign_category_id: Optional[int] = None
    is_active: Optional[bool] = None


class Rule(RuleBase):
    id: int
    created_at: datetime
    category: Optional[Category] = None

    class Config:
        from_attributes = True


# Import Schemas
class ImportResult(BaseModel):
    id: int
    filename: Optional[str]
    import_date: datetime
    transactions_total: int
    transactions_new: int
    transactions_duplicate: int
    transactions_error: int
    status: str

    class Config:
        from_attributes = True


# Statistics Schemas
class DashboardSummary(BaseModel):
    current_balance: Optional[Decimal] = None
    income_current_month: Decimal
    expenses_current_month: Decimal
    income_previous_month: Decimal
    expenses_previous_month: Decimal
    uncategorized_count: int
    top_categories: List[dict]
    recent_transactions: List[Transaction]


class CategoryStats(BaseModel):
    category_id: Optional[int]
    category_name: str
    category_color: Optional[str]
    total: Decimal
    average_monthly: Decimal
    transaction_count: int
    children: List["CategoryStats"] = []


class TimeSeriesPoint(BaseModel):
    date: str
    income: Decimal
    expenses: Decimal


class StatsByCategory(BaseModel):
    categories: List[CategoryStats]
    total_income: Decimal
    total_expenses: Decimal


class StatsOverTime(BaseModel):
    data: List[TimeSeriesPoint]
    total_income: Decimal
    total_expenses: Decimal
