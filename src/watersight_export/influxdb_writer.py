"""Write water usage data to InfluxDB v2."""
import logging
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

log = logging.getLogger(__name__)


class InfluxDBWriter:
    """Writes water usage points to InfluxDB v2."""

    def __init__(self, url: str, token: str, org: str, bucket: str = "water_insights"):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def write_hourly(self, records: list[dict], since_ts: int = 0) -> int:
        """Write hourly records to InfluxDB. Returns count of points written."""
        points = []
        for rec in records:
            ts = rec.get("read_datetime", 0)
            if ts <= since_ts:
                continue
            gallons = rec.get("gallons") or 0
            leak = rec.get("leak_gallons") or 0
            p = (
                Point("water_usage")
                .tag("resolution", "hourly")
                .tag("source", "watersight")
                .field("gallons", float(gallons))
                .field("leak_gallons", float(leak))
                .time(datetime.fromtimestamp(ts, tz=timezone.utc), WritePrecision.S)
            )
            points.append(p)

        if points:
            # Write in batches of 5000
            batch_size = 5000
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                self.write_api.write(bucket=self.bucket, record=batch)
                log.info("Wrote batch %d-%d of %d hourly points", i, i + len(batch), len(points))

        log.info("Wrote %d hourly points to InfluxDB (skipped %d old)", len(points), len(records) - len(points))
        return len(points)

    def write_daily(self, chart_data: dict) -> int:
        """Write daily records extracted from weatherConsumptionChart."""
        daily = chart_data.get("data", {}).get("chartData", {}).get("dailyData", {})
        categories = daily.get("categories", [])
        you_values = daily.get("you", [])

        if len(categories) != len(you_values):
            log.warning("Category/value length mismatch: %d vs %d", len(categories), len(you_values))
            count = min(len(categories), len(you_values))
        else:
            count = len(categories)

        points = []
        for i in range(count):
            date_str = categories[i]
            gallons = you_values[i]
            if gallons is None:
                continue
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            p = (
                Point("water_usage")
                .tag("resolution", "daily")
                .tag("source", "watersight")
                .field("gallons", float(gallons))
                .time(dt, WritePrecision.S)
            )
            points.append(p)

        if points:
            batch_size = 5000
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                self.write_api.write(bucket=self.bucket, record=batch)
            log.info("Wrote %d daily points to InfluxDB", len(points))

        return len(points)

    def get_latest_timestamp(self) -> int:
        """Query the most recent hourly record timestamp from InfluxDB."""
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -10y)
          |> filter(fn: (r) => r._measurement == "water_usage")
          |> filter(fn: (r) => r.resolution == "hourly")
          |> filter(fn: (r) => r._field == "gallons")
          |> last()
        '''
        try:
            result = self.client.query_api().query(query, org=self.org)
            for table in result:
                for record in table.records:
                    return int(record.get_time().timestamp())
        except Exception as exc:
            log.warning("Could not query latest timestamp: %s", exc)
        return 0

    def close(self):
        self.client.close()
