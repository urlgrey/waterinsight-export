"""Publish water usage sensors to Home Assistant via MQTT Discovery.

This is the **recommended** way to expose sensors to Home Assistant.

Compared to the REST API path (`HAPublisher`), MQTT Discovery:
  * Survives Home Assistant restarts. State set via `POST /api/states/<entity>` is
    held only in HA's in-memory state machine and is wiped on restart unless an
    integration reasserts it. MQTT topics are retained on the broker, so HA
    repopulates the entity on boot.
  * Creates real, persistent entities visible in the device registry, with
    proper unique_id, device grouping, availability tracking, and Energy
    dashboard support.
  * Lets us declare an `availability_topic` so HA can show the sensor as
    `unavailable` if the exporter is down — instead of silently going stale.

Topic layout::

    <prefix>/sensor/watersight_water/<sensor>/config   (discovery, retained)
    <prefix>/sensor/watersight_water/<sensor>/state    (state,     retained)
    <prefix>/sensor/watersight_water/availability      (LWT,       retained)

Where `<prefix>` defaults to ``homeassistant`` (HA's default discovery prefix).
"""
from __future__ import annotations

import json
import logging
import socket
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


DEVICE_INFO = {
    "identifiers": ["watersight_export"],
    "name": "WaterInsight Export",
    "manufacturer": "watersight-export",
    "model": "Hourly Water Usage Exporter",
    "sw_version": "1.0",
}


# (sensor_key, friendly_name, unit, device_class, state_class, icon, extra_attrs?)
SENSORS: list[dict[str, Any]] = [
    {
        "key": "hourly_gallons",
        "name": "Water Usage Latest Hour",
        "object_id": "water_usage_hourly_gallons",
        "unit": "gal",
        "device_class": "water",
        "state_class": "measurement",
        "icon": "mdi:water-outline",
    },
    {
        "key": "daily_gallons",
        "name": "Water Usage Yesterday",
        "object_id": "water_usage_daily_gallons",
        "unit": "gal",
        "device_class": "water",
        "state_class": "measurement",
        "icon": "mdi:water",
    },
    {
        "key": "monthly_gallons",
        "name": "Water Usage This Month",
        "object_id": "water_usage_monthly_gallons",
        "unit": "gal",
        "device_class": "water",
        # total_increasing within a month — use total with last_reset attribute
        # set to the start of the month so HA's statistics handles the rollover.
        "state_class": "total",
        "icon": "mdi:water-pump",
    },
    {
        "key": "total_gallons",
        "name": "Water Meter Total",
        "object_id": "water_usage_total_gallons",
        "unit": "gal",
        "device_class": "water",
        "state_class": "total_increasing",
        "icon": "mdi:water-check",
    },
    {
        "key": "last_updated",
        "name": "Water Data Last Updated",
        "object_id": "water_usage_last_updated",
        "unit": None,
        "device_class": "timestamp",
        "state_class": None,
        "icon": "mdi:clock-check-outline",
    },
]


class MQTTPublisher:
    """Publishes water-usage sensors to Home Assistant via MQTT Discovery."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        discovery_prefix: str = "homeassistant",
        node_id: str = "watersight_water",
        client_id: str | None = None,
    ):
        self.host = host
        self.port = port
        self.discovery_prefix = discovery_prefix.rstrip("/")
        self.node_id = node_id
        self.availability_topic = (
            f"{self.discovery_prefix}/sensor/{self.node_id}/availability"
        )

        self.client = mqtt.Client(
            client_id=client_id or f"watersight-export-{socket.gethostname()}",
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
        if username:
            self.client.username_pw_set(username, password)
        # Last Will: if we drop off, broker tells HA we're "offline".
        self.client.will_set(
            self.availability_topic, payload="offline", qos=1, retain=True
        )

        self._discovery_published = False
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    # ---- connection lifecycle ------------------------------------------------

    def _on_connect(self, client, _userdata, _flags, rc):
        if rc == 0:
            log.info("MQTT connected to %s:%s", self.host, self.port)
            client.publish(self.availability_topic, "online", qos=1, retain=True)
        else:
            log.error("MQTT connect failed rc=%s", rc)

    def _on_disconnect(self, _client, _userdata, rc):
        if rc != 0:
            log.warning("MQTT disconnected unexpectedly rc=%s", rc)

    def connect(self) -> None:
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()
        # Publish discovery once per process.
        if not self._discovery_published:
            self.publish_discovery()
            self._discovery_published = True

    def close(self) -> None:
        try:
            self.client.publish(
                self.availability_topic, "offline", qos=1, retain=True
            )
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    # ---- topics --------------------------------------------------------------

    def _state_topic(self, key: str) -> str:
        return f"{self.discovery_prefix}/sensor/{self.node_id}/{key}/state"

    def _config_topic(self, key: str) -> str:
        return f"{self.discovery_prefix}/sensor/{self.node_id}/{key}/config"

    # ---- discovery -----------------------------------------------------------

    def publish_discovery(self) -> None:
        """Publish HA Discovery configs for every sensor (retained)."""
        for s in SENSORS:
            payload: dict[str, Any] = {
                "name": s["name"],
                "object_id": s["object_id"],
                "unique_id": f"watersight_{s['key']}",
                "state_topic": self._state_topic(s["key"]),
                "availability_topic": self.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": DEVICE_INFO,
            }
            if s.get("unit"):
                payload["unit_of_measurement"] = s["unit"]
            if s.get("device_class"):
                payload["device_class"] = s["device_class"]
            if s.get("state_class"):
                payload["state_class"] = s["state_class"]
            if s.get("icon"):
                payload["icon"] = s["icon"]

            # Per HA docs: total sensors should advertise a JSON-attribute topic
            # carrying last_reset when applicable. We embed that in the state
            # payload via JSON attributes for the monthly counter.
            if s["key"] == "monthly_gallons":
                payload["json_attributes_topic"] = self._state_topic(s["key"])
                payload["last_reset_value_template"] = "{{ value_json.last_reset }}"
                payload["value_template"] = "{{ value_json.gallons }}"

            self.client.publish(
                self._config_topic(s["key"]),
                json.dumps(payload),
                qos=1,
                retain=True,
            )
        log.info("MQTT discovery published for %d sensors", len(SENSORS))

    # ---- publish methods (mirror HAPublisher) --------------------------------

    def publish_hourly(self, gallons: float, timestamp: int) -> None:
        self._publish("hourly_gallons", round(gallons, 2))
        log.info(
            "Published hourly water usage: %.2f gal (reading from %s)",
            gallons,
            datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
        )

    def publish_daily(self, gallons: float, date: str) -> None:
        self._publish("daily_gallons", round(gallons, 1))
        log.info("Published daily water usage: %.1f gal (%s)", gallons, date)

    def publish_monthly(
        self, gallons: float, month: str | None = None, last_reset: str | None = None
    ) -> None:
        # JSON payload with last_reset so HA statistics roll over cleanly.
        if last_reset is None:
            now = datetime.now(timezone.utc)
            month_start = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            last_reset = month_start.isoformat()
        payload = {"gallons": round(gallons, 1), "last_reset": last_reset}
        self.client.publish(
            self._state_topic("monthly_gallons"),
            json.dumps(payload),
            qos=1,
            retain=True,
        )
        label = month or datetime.now(timezone.utc).strftime("%Y-%m")
        log.info("Published monthly water usage: %.1f gal (%s)", gallons, label)

    def publish_total(self, total_gallons: float) -> None:
        self._publish("total_gallons", round(total_gallons, 1))
        log.info("Published total water usage: %.1f gal", total_gallons)

    def publish_last_updated(self, timestamp: int) -> None:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        self._publish("last_updated", dt)
        log.info("Published last updated: %s", dt)

    # ---- internals -----------------------------------------------------------

    def _publish(self, key: str, value: Any) -> None:
        topic = self._state_topic(key)
        payload = str(value)
        info = self.client.publish(topic, payload, qos=1, retain=True)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.error("MQTT publish to %s failed rc=%s", topic, info.rc)
