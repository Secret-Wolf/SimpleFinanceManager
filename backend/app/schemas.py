from pydantic import BaseModel, field_validator
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
import re


# Auth Schemas
class UserRegister(BaseModel):
    email: str
    password: str
    display_name: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v.strip().lower()):
            raise ValueError("Ungültige E-Mail-Adresse")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 12:
            raise ValueError("Passwort muss mindestens 12 Zeichen lang sein")
        if not re.search(r'[A-Z]', v):
            raise ValueError("Passwort muss mindestens einen Großbuchstaben enthalten")
        if not re.search(r'[a-z]', v):
            raise ValueError("Passwort muss mindestens einen Kleinbuchstaben enthalten")
        if not re.search(r'[0-9]', v):
            raise ValueError("Passwort muss mindestens eine Zahl enthalten")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v):
        v = v.strip()
        if len(v) < 2 or len(v) > 50:
            raise ValueError("Name muss zwischen 2 und 50 Zeichen lang sein")
        return v


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    is_active: bool
    is_admin: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 12:
            raise ValueError("Passwort muss mindestens 12 Zeichen lang sein")
        if not re.search(r'[A-Z]', v):
            raise ValueError("Passwort muss mindestens einen Großbuchstaben enthalten")
        if not re.search(r'[a-z]', v):
            raise ValueError("Passwort muss mindestens einen Kleinbuchstaben enthalten")
        if not re.search(r'[0-9]', v):
            raise ValueError("Passwort muss mindestens eine Zahl enthalten")
        return v


class AdminUserUpdate(BaseModel):
    is_active: Optional[bool] = None
    display_name: Optional[str] = None
    new_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if v is None:
            return v
        if len(v) < 12:
            raise ValueError("Passwort muss mindestens 12 Zeichen lang sein")
        if not re.search(r'[A-Z]', v):
            raise ValueError("Passwort muss mindestens einen Großbuchstaben enthalten")
        if not re.search(r'[a-z]', v):
            raise ValueError("Passwort muss mindestens einen Kleinbuchstaben enthalten")
        if not re.search(r'[0-9]', v):
            raise ValueError("Passwort muss mindestens eine Zahl enthalten")
        return v


# Household Schemas
class HouseholdCreate(BaseModel):
    name: str


class HouseholdResponse(BaseModel):
    id: int
    name: str
    created_by: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HouseholdMemberResponse(BaseModel):
    id: int
    household_id: int
    user_id: int
    user_email: Optional[str] = None
    user_display_name: Optional[str] = None
    role: str
    joined_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HouseholdDetailResponse(HouseholdResponse):
    members: List[HouseholdMemberResponse] = []


class HouseholdInviteCreate(BaseModel):
    email: str


class HouseholdInviteResponse(BaseModel):
    id: int
    household_id: int
    household_name: Optional[str] = None
    invited_by: int
    invited_by_name: Optional[str] = None
    invited_email: str
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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


class AccountCreate(BaseModel):
    name: str
    account_type: Optional[str] = "giro"


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


class TransactionCreate(TransactionBase):
    account_iban: str


class ManualTransactionCreate(BaseModel):
    """Schema fuer manuelle Transaktionen (Bargeld, Geschenke, etc.)"""
    booking_date: date
    amount: Decimal  # Positiv = Einnahme, Negativ = Ausgabe
    description: str  # Beschreibung/Verwendungszweck
    category_id: Optional[int] = None
    notes: Optional[str] = None
    account_id: Optional[int] = None  # If set, use this account instead of cash


class TransactionUpdate(BaseModel):
    category_id: Optional[int] = None
    notes: Optional[str] = None
    is_shared: Optional[bool] = None
    shared_household_id: Optional[int] = None
    amount: Optional[Decimal] = None
    counterpart_name: Optional[str] = None
    purpose: Optional[str] = None
    booking_date: Optional[date] = None


class BulkSharedRequest(BaseModel):
    transaction_ids: List[int]
    is_shared: bool = True


class Transaction(TransactionBase):
    id: int
    import_hash: str
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    account_iban: Optional[str] = None
    bank_name: Optional[str] = None
    is_split_parent: bool = False
    is_shared: bool = False
    shared_household_id: Optional[int] = None
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
    assign_shared: bool = False
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
    assign_shared: Optional[bool] = None
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
    shared_expenses_current_month: Decimal = Decimal("0")
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


# Shared Statistics
class ProfileExpenses(BaseModel):
    profile_id: int
    profile_name: str
    profile_color: str
    total_paid: Decimal


class SharedSummary(BaseModel):
    total_shared_expenses: Decimal
    by_profile: List[ProfileExpenses]
    by_category: List[CategoryStats]
