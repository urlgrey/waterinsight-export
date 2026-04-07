"""Publish water usage sensors to Home Assistant via REST API."""
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)


class HAPublisher:
    """Pushes sensor state to Home Assistant."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def publish_daily(self, gallons: float, date: str | None = None) -> None:
        """Set sensor.water_usage_daily_gallons."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._set_state(
            entity_id="sensor.water_usage_daily_gallons",
            state=round(gallons, 1),
            attributes={
                "unit_of_measurement": "gal",
                "device_class": "water",
                "state_class": "total_increasing",
                "friendly_name": "Water Usage Today",
                "date": date,
                "icon": "mdi:water",
            },
        )
        log.info("Published daily water usage: %.1f gal (%s)", gallons, date)

    def publish_monthly(self, gallons: float, month: str | None = None) -> None:
        """Set sensor.water_usage_monthly_gallons."""
        if month is None:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
        self._set_state(
            entity_id="sensor.water_usage_monthly_gallons",
            state=round(gallons, 1),
            attributes={
                "unit_of_measurement": "gal",
                "device_class": "water",
                "state_class": "total_increasing",
                "friendly_name": "Water Usage This Month",
                "month": month,
                "icon": "mdi:water-pump",
            },
        )
        log.info("Published monthly water usage: %.1f gal (%s)", gallons, month)

    def _set_state(self, entity_id: str, state: float, attributes: dict) -> None:
        url = f"{self.url}/api/states/{entity_id}"
        payload = {"state": str(state), "attributes": attributes}
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            log.error("Failed to publish %s: %s", entity_id, exc)
