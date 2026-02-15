from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String, default="#2563eb")
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    accounts = relationship("Account", back_populates="profile")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    iban = Column(String, unique=True, nullable=False)
    bic = Column(String)
    bank_name = Column(String)
    account_type = Column(String)  # "giro", "savings", "credit"
    is_active = Column(Boolean, default=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    transactions = relationship("Transaction", back_populates="account")
    profile = relationship("Profile", back_populates="accounts")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"))
    full_path = Column(String)  # Cache: "Auto:Tanken"
    color = Column(String)  # Hex-Farbe
    icon = Column(String)
    budget_monthly = Column(Numeric(10, 2))
    created_at = Column(DateTime, default=func.now())

    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent")
    transactions = relationship("Transaction", back_populates="category")
    rules = relationship("CategorizationRule", back_populates="category")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    import_hash = Column(String, unique=True, nullable=False)

    # Kontodaten
    account_id = Column(Integer, ForeignKey("accounts.id"))
    account_name = Column(String)
    account_iban = Column(String)
    account_bic = Column(String)
    bank_name = Column(String)

    # Buchungsdaten
    booking_date = Column(Date, nullable=False)
    value_date = Column(Date)

    # Gegenseite
    counterpart_name = Column(String)
    counterpart_iban = Column(String)
    counterpart_bic = Column(String)

    # Transaktionsdetails
    booking_type = Column(String)
    purpose = Column(Text)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="EUR")
    balance_after = Column(Numeric(10, 2))

    # Kategorisierung
    category_id = Column(Integer, ForeignKey("categories.id"))

    # Splitbuchung
    parent_transaction_id = Column(Integer, ForeignKey("transactions.id"))
    is_split_parent = Column(Boolean, default=False)

    # Gemeinsame Ausgabe
    is_shared = Column(Boolean, default=False)

    # Benutzerdaten
    notes = Column(Text)
    tags = Column(String)  # Komma-separiert

    # Metadaten
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Original-Daten aus Import
    original_category = Column(String)
    creditor_id = Column(String)
    mandate_reference = Column(String)

    # Relationships
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    parent_transaction = relationship("Transaction", remote_side=[id], back_populates="split_children")
    split_children = relationship("Transaction", back_populates="parent_transaction")


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    priority = Column(Integer, default=0)

    # Matching-Kriterien
    match_counterpart_name = Column(String)  # LIKE-Pattern
    match_counterpart_iban = Column(String)
    match_purpose = Column(String)  # LIKE-Pattern
    match_booking_type = Column(String)
    match_amount_min = Column(Numeric(10, 2))
    match_amount_max = Column(Numeric(10, 2))

    # Aktion
    assign_category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    assign_shared = Column(Boolean, default=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    category = relationship("Category", back_populates="rules")


class Import(Base):
    __tablename__ = "imports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String)
    import_date = Column(DateTime, default=func.now())
    transactions_total = Column(Integer)
    transactions_new = Column(Integer)
    transactions_duplicate = Column(Integer)
    transactions_error = Column(Integer, default=0)
    status = Column(String)  # "success", "partial", "failed"
