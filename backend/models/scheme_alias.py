from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SchemeAlias(Base):
    """Maps a raw name as it appears on a broker statement to a scheme code.

    Required because AMFI scheme names are not unique (the same fund name
    covers Direct/Regular x Growth/IDCW variants under different codes) and
    because different brokers spell the same fund differently. Built up by
    the import wizard whenever the user resolves an unmapped name.
    """

    __tablename__ = "scheme_aliases"
    __table_args__ = (UniqueConstraint("user_id", "raw_name", name="uq_scheme_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    raw_name: Mapped[str] = mapped_column(String(255))
    scheme_code: Mapped[str] = mapped_column(ForeignKey("schemes.scheme_code"), index=True)
