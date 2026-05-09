# waterinsight-export

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
docker run --rm --env-file .env -v watersight-data:/data skidder/waterinsight-export:latest
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
| `HA_URL` | No | — | Home Assistant URL for **REST API** publishing (legacy; entities don't survive HA restarts) |
| `HA_TOKEN` | No | — | Home Assistant long-lived access token (paired with `HA_URL`) |
| `MQTT_HOST` | No | — | MQTT broker host for **HA Discovery** publishing (recommended; persists across HA restarts) |
| `MQTT_PORT` | No | `1883` | MQTT broker port |
| `MQTT_USERNAME` | No | — | MQTT broker username |
| `MQTT_PASSWORD` | No | — | MQTT broker password |
| `MQTT_DISCOVERY_PREFIX` | No | `homeassistant` | HA MQTT discovery prefix |
| `SYNC_INTERVAL_HOURS` | No | `6` | Hours between syncs in daemon mode |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `DATA_DIR` | No | `/data` | Directory for persistent state |

## Architecture

```
WaterInsight Portal
        │
        ▼ (login + REST API)
 waterinsight-export
        │
        ├──▶ InfluxDB v2 (hourly + daily time series)
        │
        ├──▶ Home Assistant via MQTT Discovery (recommended)
        │         retained topics under `homeassistant/sensor/watersight_water/...`
        │         entities persist across HA restarts and broker reconnects
        │
        └──▶ Home Assistant via REST API (legacy)
                  state set via `POST /api/states/<id>` is in-memory only —
                  entities disappear when HA restarts and only come back the
                  next time this exporter runs (up to `SYNC_INTERVAL_HOURS`
                  later)
```

### Home Assistant integration: pick one

- **MQTT (recommended):** set `MQTT_HOST` (and credentials). The exporter
  publishes HA Discovery configs once at startup, then writes retained state
  to per-sensor topics. Sensors appear automatically as a single
  *WaterInsight Export* device with availability tracking via LWT.
- **REST API (legacy):** set `HA_URL` and `HA_TOKEN`. Works, but the entities
  it creates are not persistent — every HA restart blanks them until the
  next sync cycle pushes state again.

You can enable both at once; MQTT will write to the canonical entities and
the REST publisher will continue writing to the same `entity_id` names for
backward compatibility.

## CI/CD

GitHub Actions builds multi-arch Docker images on every push to `main` and on version tags (`v*`). Images are pushed to Docker Hub as `skidder/waterinsight-export`.

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
