import concurrent.futures
import re
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models import Account, CategorizationRule, Transaction

_regex_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="regex")
_REGEX_TIMEOUT = 2.0
_REGEX_INPUT_LIMIT = 2000


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
            compiled = re.compile(regex_pattern, flags)
        except re.error:
            return pattern.lower() in text.lower()

        limited_text = text[:_REGEX_INPUT_LIMIT]
        future = _regex_executor.submit(compiled.search, limited_text)
        try:
            return bool(future.result(timeout=_REGEX_TIMEOUT))
        except concurrent.futures.TimeoutError:
            return False

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


def _user_account_ids(db: Session, user_id: int) -> List[int]:
    return [a.id for a in db.query(Account.id).filter(Account.user_id == user_id).all()]


def _active_rules_for_user(db: Session, user_id: int, rule_ids: Optional[List[int]] = None) -> List[CategorizationRule]:
    """Active rules belonging to one user, highest priority first.

    rule_ids optionally restricts to a selection (Regel-Sets); IDs of other
    users' rules are silently dropped by the user_id filter."""
    query = db.query(CategorizationRule).filter(
        CategorizationRule.is_active == True,
        CategorizationRule.user_id == user_id,
    )
    if rule_ids is not None:
        query = query.filter(CategorizationRule.id.in_(rule_ids))
    return query.order_by(CategorizationRule.priority.desc()).all()


def _first_matching_rule(rules: List[CategorizationRule], transaction: Transaction) -> Optional[dict]:
    for rule in rules:
        if match_rule(transaction, rule):
            return {"category_id": rule.assign_category_id, "assign_shared": rule.assign_shared}
    return None


def categorize_transaction(db: Session, transaction: Transaction, user_id: int) -> Optional[dict]:
    """Find a matching category/shared flag using ONLY the given user's active rules."""
    return _first_matching_rule(_active_rules_for_user(db, user_id), transaction)


def apply_rules_to_uncategorized(db: Session, user_id: int, rule_ids: Optional[List[int]] = None) -> int:
    """Apply the user's rules to the user's uncategorized transactions. Returns count.

    User-scoped: only the user's own accounts' transactions and own rules are touched
    (a user's rules must never categorize another user's transactions).
    rule_ids optionally restricts which rules run (Regel-Sets)."""
    account_ids = _user_account_ids(db, user_id)
    rules = _active_rules_for_user(db, user_id, rule_ids)
    if not account_ids or not rules:
        return 0

    uncategorized = db.query(Transaction).filter(
        Transaction.category_id == None,
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False,
        Transaction.account_id.in_(account_ids),
    ).all()

    categorized_count = 0
    for transaction in uncategorized:
        result = _first_matching_rule(rules, transaction)
        if result:
            transaction.category_id = result["category_id"]
            if result["assign_shared"]:
                transaction.is_shared = True
            categorized_count += 1

    db.commit()
    return categorized_count


def apply_rules_to_all(db: Session, user_id: int, rule_ids: Optional[List[int]] = None) -> int:
    """Apply the user's rules to ALL their transactions, overwriting categories. Returns count.
    rule_ids optionally restricts which rules run (Regel-Sets)."""
    account_ids = _user_account_ids(db, user_id)
    rules = _active_rules_for_user(db, user_id, rule_ids)
    if not account_ids or not rules:
        return 0

    transactions = db.query(Transaction).filter(
        Transaction.is_split_parent == False,
        Transaction.is_transfer == False,
        Transaction.account_id.in_(account_ids),
    ).all()

    categorized_count = 0
    for transaction in transactions:
        result = _first_matching_rule(rules, transaction)
        if result:
            transaction.category_id = result["category_id"]
            if result["assign_shared"]:
                transaction.is_shared = True
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
