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

    def publish_hourly(self, gallons: float, timestamp: int) -> None:
        """Set sensor.water_usage_hourly_gallons — most recent hourly reading."""
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        self._set_state(
            entity_id="sensor.water_usage_hourly_gallons",
            state=round(gallons, 2),
            attributes={
                "unit_of_measurement": "gal",
                "device_class": "water",
                "state_class": "measurement",
                "friendly_name": "Water Usage (Latest Hour)",
                "reading_time": dt.isoformat(),
                "icon": "mdi:water-outline",
            },
        )
        log.info("Published hourly water usage: %.2f gal (reading from %s)", gallons, dt.isoformat())

    def publish_daily(self, gallons: float, date: str) -> None:
        """Set sensor.water_usage_daily_gallons — yesterday's complete total."""
        self._set_state(
            entity_id="sensor.water_usage_daily_gallons",
            state=round(gallons, 1),
            attributes={
                "unit_of_measurement": "gal",
                "device_class": "water",
                "state_class": "measurement",
                "friendly_name": "Water Usage Yesterday",
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
                "state_class": "measurement",
                "friendly_name": "Water Usage This Month",
                "month": month,
                "icon": "mdi:water-pump",
            },
        )
        log.info("Published monthly water usage: %.1f gal (%s)", gallons, month)

    def publish_total(self, total_gallons: float) -> None:
        """Set sensor.water_usage_total_gallons — cumulative meter reading for HA Energy dashboard."""
        self._set_state(
            entity_id="sensor.water_usage_total_gallons",
            state=round(total_gallons, 1),
            attributes={
                "unit_of_measurement": "gal",
                "device_class": "water",
                "state_class": "total_increasing",
                "friendly_name": "Water Meter Total",
                "icon": "mdi:water-check",
                "last_reset": None,
            },
        )
        log.info("Published total water usage: %.1f gal", total_gallons)

    def publish_last_updated(self, timestamp: int) -> None:
        """Set sensor.water_usage_last_updated — when the latest data was recorded."""
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        self._set_state(
            entity_id="sensor.water_usage_last_updated",
            state=dt.isoformat(),
            attributes={
                "device_class": "timestamp",
                "friendly_name": "Water Data Last Updated",
                "icon": "mdi:clock-check-outline",
            },
        )
        log.info("Published last updated: %s", dt.isoformat())

    def _set_state(self, entity_id: str, state: float | str, attributes: dict) -> None:
        url = f"{self.url}/api/states/{entity_id}"
        payload = {"state": str(state), "attributes": attributes}
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            log.error("Failed to publish %s: %s", entity_id, exc)
