"""String-valued enums shared across models, services and schemas.

Stored as plain VARCHAR (via sqlalchemy.Enum's default SQLite behaviour) so
they read as ordinary text in the database file - easy to inspect with any
SQLite browser without needing to know SQLAlchemy's enum encoding.
"""

from enum import StrEnum


class TransactionType(StrEnum):
    PURCHASE = "PURCHASE"
    REDEMPTION = "REDEMPTION"


class TransactionSource(StrEnum):
    MANUAL = "MANUAL"
    SIP = "SIP"
    IMPORT = "IMPORT"


class SipFrequency(StrEnum):
    MONTHLY = "MONTHLY"
    BIWEEKLY = "BIWEEKLY"


class ImportRowAction(StrEnum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"
    UNMAPPED = "UNMAPPED"
    ERROR = "ERROR"


class ImportBatchStatus(StrEnum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
