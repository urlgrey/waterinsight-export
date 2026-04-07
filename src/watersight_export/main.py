"""WaterSight Export — main entry point."""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .watersight_client import WaterSightClient
from .influxdb_writer import InfluxDBWriter
from .ha_publisher import HAPublisher

log = logging.getLogger("watersight_export")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SYNC_FILE = DATA_DIR / "last_sync.json"


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def setup_logging() -> None:
    level = getattr(logging, env("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_sync_state() -> dict:
    if SYNC_FILE.exists():
        return json.loads(SYNC_FILE.read_text())
    return {}


def save_sync_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SYNC_FILE.write_text(json.dumps(state, indent=2))


def compute_today_and_month(hourly: list[dict]) -> tuple[float, float]:
    """Sum gallons for today and current month from hourly data."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    today_ts = int(today_start.timestamp())
    month_ts = int(month_start.timestamp())

    today_gal = 0.0
    month_gal = 0.0
    for rec in hourly:
        ts = rec.get("read_datetime", 0)
        gal = rec.get("gallons") or 0
        if ts >= month_ts:
            month_gal += gal
        if ts >= today_ts:
            today_gal += gal

    return today_gal, month_gal


def sync_once(
    client: WaterSightClient,
    influx: InfluxDBWriter | None,
    ha: HAPublisher | None,
) -> None:
    """Run a single sync cycle."""
    state = load_sync_state()
    since_ts = state.get("last_hourly_ts", 0)

    # If InfluxDB is configured and we have no local state, check InfluxDB for last ts
    if since_ts == 0 and influx:
        since_ts = influx.get_latest_timestamp()
        if since_ts:
            log.info("Resuming from InfluxDB latest timestamp: %d", since_ts)

    is_backfill = since_ts == 0
    if is_backfill:
        log.info("No previous sync found — performing full historical backfill")
    else:
        log.info("Incremental sync since timestamp %d (%s)",
                 since_ts, datetime.fromtimestamp(since_ts, tz=timezone.utc).isoformat())

    # 1. Login
    client.login()

    # 2. Fetch hourly data
    log.info("Fetching hourly data from RealTimeChart...")
    hourly = client.get_realtime()
    log.info("Received %d hourly records", len(hourly))

    # 3. Write to InfluxDB
    written = 0
    if influx and hourly:
        written = influx.write_hourly(hourly, since_ts=since_ts)

    # 4. On first run, also write daily data
    if is_backfill and influx:
        log.info("Backfill: fetching daily data...")
        daily = client.get_daily()
        influx.write_daily(daily)

    # 5. Publish to Home Assistant
    if ha and hourly:
        today_gal, month_gal = compute_today_and_month(hourly)
        ha.publish_daily(today_gal)
        ha.publish_monthly(month_gal)

    # 6. Save sync state
    if hourly:
        max_ts = max(r.get("read_datetime", 0) for r in hourly)
        state["last_hourly_ts"] = max_ts
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        state["records_written"] = written
        save_sync_state(state)

    log.info("Sync complete — %d new points written", written)


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="WaterSight Export")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    args = parser.parse_args()

    # Validate required env vars
    email = env("WATERSIGHT_EMAIL")
    password = env("WATERSIGHT_PASSWORD")
    if not email or not password:
        log.error("WATERSIGHT_EMAIL and WATERSIGHT_PASSWORD are required")
        sys.exit(1)

    base_url = env("WATERSIGHT_URL", "https://benicia.waterinsight.com")

    client = WaterSightClient(base_url=base_url, email=email, password=password)

    # Optional: InfluxDB
    influx = None
    influx_url = env("INFLUXDB_URL")
    influx_token = env("INFLUXDB_TOKEN")
    if influx_url and influx_token:
        influx = InfluxDBWriter(
            url=influx_url,
            token=influx_token,
            org=env("INFLUXDB_ORG", ""),
            bucket=env("INFLUXDB_BUCKET", "water_insights"),
        )
        log.info("InfluxDB output enabled: %s", influx_url)
    else:
        log.warning("InfluxDB not configured — skipping InfluxDB writes")

    # Optional: Home Assistant
    ha = None
    ha_url = env("HA_URL")
    ha_token = env("HA_TOKEN")
    if ha_url and ha_token:
        ha = HAPublisher(url=ha_url, token=ha_token)
        log.info("Home Assistant output enabled: %s", ha_url)
    else:
        log.warning("Home Assistant not configured — skipping HA publishes")

    interval_hours = float(env("SYNC_INTERVAL_HOURS", "6"))

    if args.daemon:
        log.info("Running in daemon mode (interval: %.1f hours)", interval_hours)
        while True:
            try:
                sync_once(client, influx, ha)
            except Exception:
                log.exception("Sync failed — will retry next cycle")
            log.info("Sleeping %.1f hours...", interval_hours)
            time.sleep(interval_hours * 3600)
    else:
        sync_once(client, influx, ha)

    if influx:
        influx.close()


if __name__ == "__main__":
    main()
