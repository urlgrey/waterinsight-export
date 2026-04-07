"""WaterInsight portal client — login + API calls."""
import logging
import re
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

DEFAULT_URL = "https://benicia.waterinsight.com"
LOGIN_PAGE = "/index.php/welcome/login"
LOGIN_POST = "/index.php/welcome/login?forceEmail=1"
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
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
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
        # 1. GET the login page to establish session cookie
        resp = self.session.get(f"{self.base_url}{LOGIN_PAGE}", timeout=30)
        resp.raise_for_status()
        log.debug("Login page status: %d, URL: %s", resp.status_code, resp.url)

        # Extract CSRF token if present (hidden input named "token")
        token_match = re.search(
            r'<input\s+type="hidden"\s+name="token"\s+value="([^"]*)"', resp.text
        )
        csrf_token = token_match.group(1) if token_match else ""

        # 2. POST credentials to the login endpoint
        post_data = {
            "email": self.email,
            "password": self.password,
            "token": csrf_token,
        }

        resp = self.session.post(
            f"{self.base_url}{LOGIN_POST}",
            data=post_data,
            timeout=30,
            allow_redirects=True,
            headers={
                "Referer": f"{self.base_url}{LOGIN_PAGE}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()

        log.debug("Post-login URL: %s", resp.url)
        log.debug("Post-login cookies: %s", list(self.session.cookies.keys()))

        # Verify login succeeded — after login we should NOT be on the login page
        if "/welcome/login" in resp.url.lower():
            # Check for error messages in the response
            error_match = re.search(r'class="error-message"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
            error_text = error_match.group(1).strip() if error_match else ""
            raise RuntimeError(
                f"Login failed — still on login page. Error: {error_text or 'unknown'}"
            )

        # Verify we have more than just PHPSESSID (successful login sets additional cookies)
        if len(self.session.cookies) < 2:
            log.warning("Login may have failed — only %d cookies set", len(self.session.cookies))

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
        resp = self.session.get(
            url,
            params=params,
            timeout=120,
            headers={"Accept": "application/json, text/html, */*"},
        )
        if resp.status_code == 403:
            log.error("403 Forbidden on %s — session may have expired, re-login needed", path)
            raise requests.exceptions.HTTPError(
                f"403 Forbidden: {path} — likely not authenticated", response=resp
            )
        resp.raise_for_status()
        return resp.json()
