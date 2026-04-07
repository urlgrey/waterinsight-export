# watersight-export

Scrapes water usage data from [WaterInsight](https://benicia.waterinsight.com) portals (used by Benicia, CA and other municipalities) and exports it to **InfluxDB v2** and **Home Assistant**.

## Features

- **Hourly water usage** — fetched from WaterInsight's RealTimeChart API
- **Daily usage** — from weatherConsumptionChart with historical backfill
- **InfluxDB v2 export** — hourly + daily data with proper timestamps
- **Home Assistant sensors** — `sensor.water_usage_daily_gallons` and `sensor.water_usage_monthly_gallons`
- **Historical backfill** — on first run, imports all available history (back to 2017+)
- **Incremental sync** — subsequent runs only fetch new data
- **Daemon mode** — runs continuously with configurable sync interval
- **Docker + docker-compose** — ready for NAS deployment
- **Multi-arch** — builds for amd64 and arm64

## Quick Start

### Docker Compose (recommended)

1. Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
# Edit .env with your values
```

2. Run:

```bash
docker compose up -d
```

### One-shot run

```bash
docker run --rm --env-file .env -v watersight-data:/data skidder/watersight-export:latest
```

(Omit `--daemon` from CMD to run once and exit.)

### Manual (without Docker)

```bash
pip install -r requirements.txt
export WATERSIGHT_EMAIL=you@email.com
export WATERSIGHT_PASSWORD=yourpass
export INFLUXDB_URL=http://192.168.1.15:8086
export INFLUXDB_TOKEN=your_token
export INFLUXDB_ORG=your_org
export HA_URL=http://192.168.1.15:8123
export HA_TOKEN=your_ha_token
python -m watersight_export.main
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WATERSIGHT_EMAIL` | **Yes** | — | WaterInsight login email |
| `WATERSIGHT_PASSWORD` | **Yes** | — | WaterInsight login password |
| `WATERSIGHT_URL` | No | `https://benicia.waterinsight.com` | WaterInsight portal base URL |
| `INFLUXDB_URL` | No | — | InfluxDB v2 URL (e.g., `http://192.168.1.15:8086`) |
| `INFLUXDB_TOKEN` | No | — | InfluxDB v2 API token |
| `INFLUXDB_ORG` | No | `""` | InfluxDB organization ID |
| `INFLUXDB_BUCKET` | No | `water_insights` | InfluxDB bucket name |
| `HA_URL` | No | — | Home Assistant URL (e.g., `http://192.168.1.15:8123`) |
| `HA_TOKEN` | No | — | Home Assistant long-lived access token |
| `SYNC_INTERVAL_HOURS` | No | `6` | Hours between syncs in daemon mode |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `DATA_DIR` | No | `/data` | Directory for persistent state |

## Architecture

```
WaterInsight Portal
        │
        ▼ (login + REST API)
 watersight-export
        │
        ├──▶ InfluxDB v2 (hourly + daily time series)
        │
        └──▶ Home Assistant (sensor.water_usage_daily_gallons,
                             sensor.water_usage_monthly_gallons)
```

## CI/CD

GitHub Actions builds multi-arch Docker images on every push to `main` and on version tags (`v*`). Images are pushed to Docker Hub as `skidder/watersight-export`.

### Required GitHub Secrets

- `DOCKERHUB_USERNAME` — Docker Hub username
- `DOCKERHUB_TOKEN` — Docker Hub access token

## Data Format

### InfluxDB

```
measurement: water_usage
tags:
  resolution: hourly | daily
  source: watersight
fields:
  gallons: float
  leak_gallons: float (hourly only)
```

### Home Assistant Sensors

- `sensor.water_usage_daily_gallons` — today's total water usage in gallons
- `sensor.water_usage_monthly_gallons` — current month's running total in gallons

## License

MIT
