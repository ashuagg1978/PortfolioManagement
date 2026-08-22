"""Import every model module so Base.metadata sees the full schema -
required for Alembic autogenerate and for metadata.create_all() in tests.
"""

from models.account import Account
from models.import_batch import ImportBatch
from models.import_row import ImportRow
from models.market_holiday import MarketHoliday
from models.portfolio_scheme import PortfolioScheme
from models.scheme import Scheme
from models.scheme_alias import SchemeAlias
from models.sip import Sip
from models.sip_skip import SipSkip
from models.transaction import Transaction
from models.user import User

__all__ = [
    "Account",
    "ImportBatch",
    "ImportRow",
    "MarketHoliday",
    "PortfolioScheme",
    "Scheme",
    "SchemeAlias",
    "Sip",
    "SipSkip",
    "Transaction",
    "User",
]
