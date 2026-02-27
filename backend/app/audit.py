"""Structured Audit Logging for security-relevant events"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

from .config import settings

# IBAN masking: show first 4 and last 4 chars
_IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2})\w{8,}(\w{4})\b")


def _mask_iban(value: str) -> str:
    """Mask IBANs in text, keeping first 4 and last 4 characters"""
    return _IBAN_RE.sub(r"\1****\2", value)


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON"""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        # Merge extra fields added via `extra=`
        for key in ("user_id", "user_email", "action", "resource", "resource_id",
                     "ip", "detail", "status"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry, ensure_ascii=False)


def _setup_audit_logger() -> logging.Logger:
    logger = logging.getLogger("audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "logs"
    )
    os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        os.path.join(log_dir, "audit.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=10,
        encoding="utf-8",
    )
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)

    # Also log to stderr in debug mode
    if settings.DEBUG:
        stderr_handler = logging.StreamHandler()
        stderr_handler.setFormatter(_JsonFormatter())
        logger.addHandler(stderr_handler)

    return logger


audit_log = _setup_audit_logger()


def log_auth_event(
    action: str,
    *,
    ip: str,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    status: str = "success",
    detail: Optional[str] = None,
):
    """Log authentication events (login, logout, register, password change, etc.)"""
    audit_log.info(
        f"AUTH: {action}",
        extra={
            "action": action,
            "user_id": user_id,
            "user_email": user_email,
            "ip": ip,
            "status": status,
            "detail": detail,
            "resource": None,
            "resource_id": None,
        },
    )


def log_data_event(
    action: str,
    *,
    user_id: int,
    resource: str,
    resource_id: Optional[int] = None,
    detail: Optional[str] = None,
):
    """Log data CRUD events (create, update, delete on sensitive resources)"""
    # Mask IBANs if present in detail
    if detail:
        detail = _mask_iban(detail)

    audit_log.info(
        f"DATA: {action} {resource}",
        extra={
            "action": action,
            "user_id": user_id,
            "user_email": None,
            "resource": resource,
            "resource_id": resource_id,
            "ip": None,
            "status": "success",
            "detail": detail,
        },
    )


def log_security_event(
    action: str,
    *,
    ip: str,
    user_id: Optional[int] = None,
    detail: Optional[str] = None,
):
    """Log security-relevant events (rate limit, forbidden access, etc.)"""
    audit_log.warning(
        f"SECURITY: {action}",
        extra={
            "action": action,
            "user_id": user_id,
            "user_email": None,
            "ip": ip,
            "status": "blocked",
            "detail": detail,
            "resource": None,
            "resource_id": None,
        },
    )
