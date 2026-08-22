"""Shared Pydantic field types for the API boundary.

Pydantic v2 serializes Decimal to a JSON *string* by default (to avoid float
imprecision) - but that breaks ordinary arithmetic in the browser
(`"12.50" * 2` is not what a React component wants). These aliases annotate
a Decimal field to serialize as a JSON number instead, while still parsing
incoming JSON numbers/strings into an exact Decimal on the way in.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

MoneyField = Annotated[Decimal, PlainSerializer(float, return_type=float)]
NavField = Annotated[Decimal, PlainSerializer(float, return_type=float)]
UnitsField = Annotated[Decimal, PlainSerializer(float, return_type=float)]
