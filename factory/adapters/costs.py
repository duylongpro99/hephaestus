"""What a media provider bills for one request, and how a station turns that into ledger entries."""

import unicodedata
from dataclasses import dataclass

from factory.contracts import CostEntry


class MediaError(RuntimeError):
    """A media provider failed, or its configuration or credentials are missing.

    `costs` holds what the station's earlier requests billed before the failure; the worker that made them
    fills it in, so the ledger stays complete when a station fails halfway."""

    costs: list[CostEntry] = []


@dataclass(frozen=True)
class MediaPrice:
    """USD per `per` units of what the provider bills (characters, images, megapixels)."""

    usd: float
    per: int = 1

    def usd_for(self, units: float) -> float:
        return round(units * self.usd / self.per, 6)


@dataclass(frozen=True)
class Charge:
    vendor: str
    model: str
    usd: float
    priced: bool = True  # False when config/media.yaml has no price; usd is then 0 and the total a floor
    dedupe_key: str | None = None  # the ledger records a keyed charge once per episode, however often it arrives


def billed_chars(text: str, wide_units: int = 1) -> int:
    """Characters as a provider bills them: East Asian wide and fullwidth characters count `wide_units` each.

    Decided per character from its Unicode property, so it holds for any language without naming one."""
    return sum(wide_units if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def charge(vendor: str, model: str, units: float, price: MediaPrice | None) -> Charge:
    if price is None:
        return Charge(vendor, model, 0.0, priced=False)
    return Charge(vendor, model, price.usd_for(units))


def ledger_entries(station: str, charges: list[Charge]) -> list[CostEntry]:
    """One entry per keyed charge, and one per vendor and model summing the station's unkeyed requests."""
    keyed = [CostEntry(station=station, vendor=c.vendor, model=c.model, usd=c.usd, priced=c.priced,
                       dedupe_key=c.dedupe_key) for c in charges if c.dedupe_key]
    totals: dict[tuple[str, str], tuple[float, bool]] = {}
    for c in charges:
        if c.dedupe_key:
            continue
        usd, priced = totals.get((c.vendor, c.model), (0.0, True))
        totals[(c.vendor, c.model)] = (usd + c.usd, priced and c.priced)
    return keyed + [CostEntry(station=station, vendor=vendor, model=model, usd=round(usd, 6), priced=priced)
                    for (vendor, model), (usd, priced) in totals.items()]
