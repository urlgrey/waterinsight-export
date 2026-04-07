"""WaterInsight portal client — login + API calls."""
import logging
import re
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

DEFAULT_URL = "https://benicia.waterinsight.com"
LOGIN_PATH = "/index.php/welcome"
REALTIME_PATH = "/index.php/rest/v1/Chart/RealTimeChart"
WEATHER_PATH = "/index.php/rest/v1/Chart/weatherConsumptionChart"
BILLING_PATH = "/index.php/rest/v1/Chart/BillingHistoryChart"
ANNUAL_PATH = "/index.php/rest/v1/Chart/annualChart"
PIE_PATH = "/index.php/rest/v1/Chart/usagePieChart"


class WaterSightClient:
    """Authenticated client for WaterInsight REST API."""

    def __init__(self, base_url: str, email: str, password: str, retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (watersight-export/0.1)",
            "Accept": "application/json, text/html, */*",
        })

    # ------------------------------------------------------------------
    def login(self) -> None:
        """Authenticate with the WaterInsight portal."""
        for attempt in range(1, self.retries + 1):
            try:
                self._do_login()
                log.info("Login successful")
                return
            except Exception as exc:
                log.warning("Login attempt %d/%d failed: %s", attempt, self.retries, exc)
                if attempt == self.retries:
                    raise
                time.sleep(2 ** attempt)

    def _do_login(self) -> None:
        # 1. GET login page to obtain CSRF token & session cookie
        resp = self.session.get(f"{self.base_url}{LOGIN_PATH}", timeout=30)
        resp.raise_for_status()

        # CodeIgniter CSRF token is typically in a hidden input
        csrf_match = re.search(
            r'<input\s+type="hidden"\s+name="([^"]+)"\s+value="([^"]+)"', resp.text
        )
        post_data: dict[str, str] = {
            "email": self.email,
            "password": self.password,
        }
        if csrf_match:
            post_data[csrf_match.group(1)] = csrf_match.group(2)

        # Detect POST target from <form action="...">
        form_match = re.search(r'<form[^>]+action="([^"]+)"', resp.text)
        login_url = form_match.group(1) if form_match else f"{self.base_url}/index.php/login"
        if login_url.startswith("/"):
            login_url = f"{self.base_url}{login_url}"

        # 2. POST credentials
        resp = self.session.post(login_url, data=post_data, timeout=30, allow_redirects=True)
        resp.raise_for_status()

        # Verify login — a successful login redirects to /index.php/home or similar
        if "login" in resp.url.lower() and "home" not in resp.url.lower():
            raise RuntimeError(f"Login likely failed — landed on {resp.url}")

    # ------------------------------------------------------------------
    def get_realtime(self) -> list[dict[str, Any]]:
        """Fetch hourly usage from RealTimeChart (can be 5MB+)."""
        data = self._api_get(REALTIME_PATH)
        return data.get("data", {}).get("series", [])

    def get_daily(self) -> dict[str, Any]:
        """Fetch daily usage from weatherConsumptionChart."""
        return self._api_get(WEATHER_PATH, params={"module": "portal", "commentary": "full"})

    def get_billing_history(self) -> list[dict[str, Any]]:
        """Fetch billing-period history."""
        data = self._api_get(BILLING_PATH, params={"flowType": "per_day", "comparison": "cohort"})
        return data.get("data", {}).get("chart_data", [])

    def get_annual(self) -> dict[str, Any]:
        """Fetch annual totals."""
        return self._api_get(ANNUAL_PATH, params={"module": "portal", "commentary": "full"})

    def get_usage_pie(self) -> dict[str, Any]:
        """Fetch usage breakdown by category."""
        return self._api_get(PIE_PATH, params={"module": "portal", "commentary": "full"})

    # ------------------------------------------------------------------
    def _api_get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        log.debug("GET %s", url)
        resp = self.session.get(url, params=params, timeout=120)
        resp.raise_for_status()
        return resp.json()
