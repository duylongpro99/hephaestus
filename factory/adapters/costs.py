"""What a media provider bills for one request, and how a station turns that into ledger entries."""

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


def charge(vendor: str, model: str, units: float, price: MediaPrice | None) -> Charge:
    if price is None:
        return Charge(vendor, model, 0.0, priced=False)
    return Charge(vendor, model, price.usd_for(units))


def ledger_entries(station: str, charges: list[Charge]) -> list[CostEntry]:
    """One entry per vendor and model, summing every request the station made."""
    totals: dict[tuple[str, str], tuple[float, bool]] = {}
    for c in charges:
        usd, priced = totals.get((c.vendor, c.model), (0.0, True))
        totals[(c.vendor, c.model)] = (usd + c.usd, priced and c.priced)
    return [CostEntry(station=station, vendor=vendor, model=model, usd=round(usd, 6), priced=priced)
            for (vendor, model), (usd, priced) in totals.items()]
