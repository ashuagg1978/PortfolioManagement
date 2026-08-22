"""FIFO lot accounting - computed on read, never persisted.

Realized gain, avg cost NAV, and units held are all *derived* from the
transaction ledger every time they're needed, rather than stored on the
redemption row. Storing them would go stale the moment an earlier purchase
is soft-deleted or corrected - at the data volumes here (low thousands of
rows per scheme) recomputing is microseconds, so there's no reason to accept
that staleness risk.

FIFO (not average cost) because Indian mutual fund capital gains are
computed FIFO by regulation, and it's the only method that also yields a
correct STCG/LTCG split per lot.

Pure functions over plain dataclasses - no DB access - so this is directly
unit-testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from models.enums import TransactionType

# Equity mutual funds: units held > 12 months are LTCG. Approximated as
# 365 days, which is the common practical proxy (a same-calendar-date
# 12-month mark is not exactly 365 days every year, but the day-count error
# is at most 1 day and never changes which side of the LTCG line a normal
# holding period falls on).
LTCG_HOLDING_DAYS = 365


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """The minimal, DB-agnostic view FIFO needs. Built by the caller from
    ORM rows (already filtered to is_deleted = false) or plain dicts alike.
    """

    id: int
    date: date
    type: str  # TransactionType
    units: Decimal
    # PURCHASE: total money invested, i.e. amount (NAV*units + commission).
    # REDEMPTION: net proceeds received, i.e. amount (NAV*units - commission).
    amount: Decimal


@dataclass(slots=True)
class Lot:
    transaction_id: int
    date: date
    units_remaining: Decimal
    cost_per_unit: Decimal  # amount / units at purchase - commission-inclusive


@dataclass(frozen=True, slots=True)
class LotConsumption:
    redemption_transaction_id: int
    redemption_date: date
    lot_transaction_id: int
    lot_date: date
    units: Decimal
    cost: Decimal
    proceeds: Decimal
    gain: Decimal
    holding_days: int
    term: str  # "LTCG" | "STCG"


class OverRedemptionError(ValueError):
    """Raised when a redemption sells more units than are held at that point
    in the ledger. The transactions service validates this before insert, so
    reaching here from run_fifo means the ledger itself is inconsistent
    (e.g. an earlier purchase was soft-deleted after this redemption was
    recorded) - worth surfacing loudly rather than silently clamping.
    """


@dataclass(frozen=True, slots=True)
class FifoResult:
    open_lots: list[Lot] = field(default_factory=list)
    consumptions: list[LotConsumption] = field(default_factory=list)

    @property
    def units_held(self) -> Decimal:
        return sum((lot.units_remaining for lot in self.open_lots), Decimal("0"))

    @property
    def cost_remaining(self) -> Decimal:
        return sum(
            (lot.units_remaining * lot.cost_per_unit for lot in self.open_lots), Decimal("0")
        )

    @property
    def avg_cost_nav(self) -> Decimal | None:
        units = self.units_held
        if units == 0:
            return None
        return self.cost_remaining / units

    @property
    def realized_gain(self) -> Decimal:
        return sum((c.gain for c in self.consumptions), Decimal("0"))


def run_fifo(entries: list[LedgerEntry]) -> FifoResult:
    """Walks entries in date order (ties broken by id, so import order is
    stable), building a FIFO lot queue from purchases and consuming it on
    each redemption.
    """
    ordered = sorted(entries, key=lambda e: (e.date, e.id))
    lots: list[Lot] = []
    consumptions: list[LotConsumption] = []

    for entry in ordered:
        if entry.type == TransactionType.PURCHASE:
            if entry.units <= 0:
                continue
            cost_per_unit = entry.amount / entry.units
            lots.append(Lot(entry.id, entry.date, entry.units, cost_per_unit))

        elif entry.type == TransactionType.REDEMPTION:
            remaining_to_sell = entry.units
            proceeds_per_unit = entry.amount / entry.units if entry.units else Decimal("0")
            while remaining_to_sell > 0:
                if not lots:
                    raise OverRedemptionError(
                        f"Transaction {entry.id} on {entry.date} redeems more units than "
                        "are held at that point in the ledger."
                    )
                lot = lots[0]
                take = min(lot.units_remaining, remaining_to_sell)
                cost = take * lot.cost_per_unit
                proceeds = take * proceeds_per_unit
                holding_days = (entry.date - lot.date).days
                consumptions.append(
                    LotConsumption(
                        redemption_transaction_id=entry.id,
                        redemption_date=entry.date,
                        lot_transaction_id=lot.transaction_id,
                        lot_date=lot.date,
                        units=take,
                        cost=cost,
                        proceeds=proceeds,
                        gain=proceeds - cost,
                        holding_days=holding_days,
                        term="LTCG" if holding_days > LTCG_HOLDING_DAYS else "STCG",
                    )
                )
                lot.units_remaining -= take
                remaining_to_sell -= take
                if lot.units_remaining == 0:
                    lots.pop(0)
        else:
            raise ValueError(f"Unknown transaction type: {entry.type!r}")

    return FifoResult(open_lots=lots, consumptions=consumptions)
