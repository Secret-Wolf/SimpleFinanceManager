from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from decimal import Decimal
import re

from ..models import Transaction, CategorizationRule, Category


def match_pattern(text: str, pattern: str) -> bool:
    """
    Match text against pattern. Supports:
    - Simple contains: "REWE" matches if text contains "REWE"
    - Wildcards: "%REWE%" or "*REWE*" for contains
    - Regex: "/Scalable.*Sparplan/i" for regex (i = case insensitive)
    """
    if not text or not pattern:
        return False

    text = text.strip()
    pattern = pattern.strip()

    # Check for regex pattern: /pattern/ or /pattern/i
    if pattern.startswith("/") and ("/" in pattern[1:]):
        # Extract regex and flags
        last_slash = pattern.rfind("/")
        regex_pattern = pattern[1:last_slash]
        flags_str = pattern[last_slash + 1:]

        flags = 0
        if "i" in flags_str:
            flags |= re.IGNORECASE

        try:
            return bool(re.search(regex_pattern, text, flags))
        except re.error:
            # Invalid regex, fall back to contains
            return pattern.lower() in text.lower()

    # Wildcard pattern (* or %)
    if "*" in pattern or "%" in pattern:
        # Convert to simple contains by removing wildcards
        clean_pattern = pattern.replace("*", "").replace("%", "").lower()
        return clean_pattern in text.lower()

    # Simple contains (case insensitive)
    return pattern.lower() in text.lower()


def match_rule(transaction: Transaction, rule: CategorizationRule) -> bool:
    """Check if a transaction matches a rule's criteria"""

    # Check counterpart name
    if rule.match_counterpart_name:
        if not match_pattern(transaction.counterpart_name, rule.match_counterpart_name):
            return False

    # Check counterpart IBAN
    if rule.match_counterpart_iban:
        if transaction.counterpart_iban != rule.match_counterpart_iban:
            return False

    # Check purpose
    if rule.match_purpose:
        if not match_pattern(transaction.purpose, rule.match_purpose):
            return False

    # Check booking type
    if rule.match_booking_type:
        if not match_pattern(transaction.booking_type, rule.match_booking_type):
            return False

    # Check amount range
    amount = abs(transaction.amount) if transaction.amount else Decimal("0")

    if rule.match_amount_min is not None:
        if amount < rule.match_amount_min:
            return False

    if rule.match_amount_max is not None:
        if amount > rule.match_amount_max:
            return False

    return True


def categorize_transaction(db: Session, transaction: Transaction) -> Optional[int]:
    """Find matching category for a transaction based on rules"""

    # Get all active rules, ordered by priority (highest first)
    rules = db.query(CategorizationRule).filter(
        CategorizationRule.is_active == True
    ).order_by(CategorizationRule.priority.desc()).all()

    for rule in rules:
        if match_rule(transaction, rule):
            return rule.assign_category_id

    return None


def apply_rules_to_transaction(db: Session, transaction: Transaction) -> bool:
    """Apply categorization rules to a single transaction"""
    if transaction.category_id is not None:
        return False

    category_id = categorize_transaction(db, transaction)
    if category_id:
        transaction.category_id = category_id
        return True

    return False


def apply_rules_to_uncategorized(db: Session) -> int:
    """Apply rules to all uncategorized transactions. Returns count of categorized."""

    uncategorized = db.query(Transaction).filter(
        Transaction.category_id == None,
        Transaction.is_split_parent == False
    ).all()

    categorized_count = 0

    for transaction in uncategorized:
        if apply_rules_to_transaction(db, transaction):
            categorized_count += 1

    db.commit()
    return categorized_count


def create_rule_from_transaction(
    db: Session,
    transaction: Transaction,
    category_id: int,
    match_type: str = "counterpart_name"
) -> CategorizationRule:
    """Create a new rule based on a transaction"""

    rule = CategorizationRule(
        assign_category_id=category_id,
        is_active=True,
        priority=0
    )

    # Set name based on transaction
    if transaction.counterpart_name:
        rule.name = f"Regel: {transaction.counterpart_name[:30]}"
    else:
        rule.name = f"Regel: {transaction.booking_type or 'Unbenannt'}"

    # Set matching criteria based on type
    if match_type == "counterpart_name" and transaction.counterpart_name:
        # Extract key part of name for matching
        name_parts = transaction.counterpart_name.split()
        if name_parts:
            rule.match_counterpart_name = f"%{name_parts[0]}%"

    elif match_type == "counterpart_iban" and transaction.counterpart_iban:
        rule.match_counterpart_iban = transaction.counterpart_iban

    elif match_type == "purpose" and transaction.purpose:
        # Use first 20 chars of purpose
        rule.match_purpose = f"%{transaction.purpose[:20]}%"

    elif match_type == "booking_type" and transaction.booking_type:
        rule.match_booking_type = transaction.booking_type

    db.add(rule)
    db.commit()
    db.refresh(rule)

    return rule
