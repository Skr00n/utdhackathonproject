"""Optional real rank-data providers (OFF by default; nothing paid is wired in).

Set RANK_PROVIDER=<name> to enable one once it is implemented and you have approved its cost.
Until then every rank grid stays labeled SIMULATED and where-it-stands stays "to be checked by hand".
"""
from __future__ import annotations

import os


class RankProvider:
    name = "base"

    def maps_rank(self, keyword: str, lat: float, lng: float, place_name: str) -> int | None:
        """Return the 1-based Google Maps position of place_name for keyword searched at (lat, lng),
        21 if not in the top 20, or None if unknown. Must come from real data, never estimated."""
        raise NotImplementedError


class NotConfigured(RankProvider):
    name = "none"

    def maps_rank(self, keyword, lat, lng, place_name):
        return None


class SerpApiProvider(RankProvider):
    """Stub for a SERP API (e.g. Google Maps results). Needs SERP_API_KEY. Not implemented on purpose:
    pick a vendor and confirm the price with the owner first."""
    name = "serp"

    def __init__(self):
        if not os.environ.get("SERP_API_KEY"):
            raise RuntimeError("RANK_PROVIDER=serp needs SERP_API_KEY")

    def maps_rank(self, keyword, lat, lng, place_name):
        raise NotImplementedError("SERP provider not implemented yet")


class PlacesProvider(RankProvider):
    """Stub for Google Places API (Text Search). Needs PLACES_API_KEY. Not implemented on purpose."""
    name = "places"

    def __init__(self):
        if not os.environ.get("PLACES_API_KEY"):
            raise RuntimeError("RANK_PROVIDER=places needs PLACES_API_KEY")

    def maps_rank(self, keyword, lat, lng, place_name):
        raise NotImplementedError("Places provider not implemented yet")


def get_rank_provider() -> RankProvider:
    name = (os.environ.get("RANK_PROVIDER") or "").strip().lower()
    if name in ("", "none", "off", "0"):
        return NotConfigured()
    return {"serp": SerpApiProvider, "places": PlacesProvider}[name]()


def has_real_ranks() -> bool:
    return not isinstance(get_rank_provider(), NotConfigured)
