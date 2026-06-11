"""Client for the app.uz.gov.ua JSON API used by the booking.uz.gov.ua frontend.

The site does not publish an official API spec, so this client targets the
endpoints used by the website's own frontend (subject to change by UZ).
If UZ changes their API, update BASE_URL / paths / response parsing below.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

BASE_URL = "https://app.uz.gov.ua"
KYIV_TZ = ZoneInfo("Europe/Kyiv")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "uk-UA",
    "Referer": "https://booking.uz.gov.ua/",
    "x-user-agent": "UZ/2 Web/1 User/guest",
    "x-client-locale": "uk",
}


class UZClientError(RuntimeError):
    pass


class UZClient:
    """Thin wrapper around the app.uz.gov.ua JSON API."""

    def __init__(self, timeout: float = 15.0):
        headers = dict(DEFAULT_HEADERS)
        headers["x-session-id"] = str(uuid.uuid4())
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "UZClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def find_station(self, query: str) -> list[dict]:
        """Look up station name -> list of {id, name} candidates."""
        resp = self._client.get("/api/stations", params={"search": query})
        resp.raise_for_status()
        return resp.json()

    def search_trains(self, station_id_from: str, station_id_to: str, date: str) -> list[dict]:
        """Search trains for a route on a given date (YYYY-MM-DD).

        Returns the raw JSON response (a list of trip objects) so callers can
        adapt to the current API shape without changing this method's
        signature.
        """
        resp = self._client.get(
            "/api/trips",
            params={
                "station_from_id": station_id_from,
                "station_to_id": station_id_to,
                "date": date,
            },
        )
        if resp.status_code >= 400:
            raise UZClientError(f"UZ API error {resp.status_code}: {resp.text[:300]}")
        return resp.json()


def extract_seat_summary(trips: list[dict]) -> list[dict]:
    """Reduce a search_trains() response to a simple per-trip seat summary.

    Returns a list of dicts: {train_number, departure, arrival, free_seats,
    wagon_classes}, where `free_seats` is the total number of available
    places across all wagon classes for that trip.
    """
    summary = []
    for trip in trips:
        train = trip.get("train", {})
        wagon_classes = train.get("wagon_classes", [])
        free_seats = sum(int(wc.get("free_seats") or 0) for wc in wagon_classes)

        summary.append(
            {
                "train_number": train.get("number") or "?",
                "departure": _format_timestamp(trip.get("depart_at")),
                "arrival": _format_timestamp(trip.get("arrive_at")),
                "free_seats": free_seats,
                "wagon_classes": [
                    {"name": wc.get("name"), "free_seats": wc.get("free_seats")}
                    for wc in wagon_classes
                    if wc.get("free_seats")
                ],
            }
        )
    return summary


def _format_timestamp(ts) -> str:
    if not ts:
        return "?"
    return datetime.fromtimestamp(int(ts), tz=KYIV_TZ).strftime("%Y-%m-%d %H:%M")
