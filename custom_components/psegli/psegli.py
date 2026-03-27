"""PSEG Long Island client.

Purely synchronous — callers in __init__.py use hass.async_add_executor_job()
to run methods off the event loop.
"""
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

import pytz
import requests
from bs4 import BeautifulSoup

from .exceptions import InvalidAuth, PSEGLIError

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30  # seconds


class PSEGLIClient:
    """PSEG Long Island API client (synchronous)."""

    def __init__(self, cookie: str) -> None:
        """Initialize the client."""
        self.cookie = cookie
        self.session = requests.Session()
        self.session.headers.update({
            "Cookie": cookie,
            "Referer": "https://mysmartenergy.nj.pseg.com/Dashboard",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Brave";v="138"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Gpc": "1"
        })

    def update_cookie(self, new_cookie: str) -> None:
        """Update the cookie in this client instance."""
        self.cookie = new_cookie
        self.session.headers.update({"Cookie": new_cookie})
        _LOGGER.debug("Updated client cookie (length=%d)", len(new_cookie))

    def test_connection(self) -> bool:
        """Test the connection to PSEG.

        Raises:
            InvalidAuth: Cookie rejected (redirected to login page).
            PSEGLIError: Network error (timeout, DNS, connection refused).
        """
        try:
            response = self.session.get(
                "https://mysmartenergy.nj.pseg.com/Dashboard",
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            # Check if we're redirected to login page (auth failure)
            if "login" in response.url.lower() or "signin" in response.url.lower():
                raise InvalidAuth("Cookie rejected — redirected to login page")

            _LOGGER.debug("PSEG connection test successful")
            return True

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
            _LOGGER.error("Network error connecting to PSEG: %s", err)
            raise PSEGLIError(f"Network error: {err}") from err
        except requests.exceptions.HTTPError as err:
            _LOGGER.error("HTTP error from PSEG: %s", err)
            raise PSEGLIError(f"HTTP error: {err}") from err

    def test_data_path(self) -> bool:
        """Probe dashboard -> chart-context auth path without fetching chart data.

        Raises:
            InvalidAuth: Cookie/session rejected for dashboard or chart context.
            PSEGLIError: Transport or HTTP failures (including chart setup 5xx).
        """
        end_date = datetime.now(tz=timezone.utc)
        start_date = end_date - timedelta(days=1)

        try:
            _, request_token = self._get_dashboard_page()
            self._setup_chart_context(request_token, start_date, end_date)
            _LOGGER.debug("PSEG data-path probe successful")
            return True
        except InvalidAuth:
            raise
        except PSEGLIError:
            raise
        except requests.exceptions.RequestException as err:
            _LOGGER.error("Transport/HTTP error during data-path probe: %s", err)
            raise PSEGLIError(f"Transport/HTTP error: {err}") from err

    def _get_dashboard_page(self) -> tuple[str, str]:
        """Get the Dashboard page and extract RequestVerificationToken."""
        dashboard_response = self.session.get(
            "https://mysmartenergy.nj.pseg.com/Dashboard",
            timeout=REQUEST_TIMEOUT,
        )
        # 4xx = likely auth issue; 5xx = transient server error
        if dashboard_response.status_code >= 500:
            raise PSEGLIError(
                f"PSEG server error (HTTP {dashboard_response.status_code})"
            )
        if dashboard_response.status_code != 200:
            raise InvalidAuth(
                f"Failed to get Dashboard page (HTTP {dashboard_response.status_code})"
            )

        # Check if redirected to login page (cookie expired mid-flow)
        if "login" in dashboard_response.url.lower() or "signin" in dashboard_response.url.lower():
            raise InvalidAuth("Cookie rejected — redirected to login page")

        request_token = self._extract_request_verification_token(dashboard_response.text)
        if not request_token:
            _LOGGER.error("Could not find RequestVerificationToken on /Dashboard")
            raise InvalidAuth("Could not find RequestVerificationToken on /Dashboard")

        return dashboard_response.text, request_token

    def _extract_request_verification_token(self, html: str) -> str | None:
        """Extract anti-forgery token from dashboard HTML or cookie header."""
        soup = BeautifulSoup(html, "html.parser")

        # Primary: hidden input in dashboard DOM (attribute order agnostic).
        token_input = soup.find("input", attrs={"name": "__RequestVerificationToken"})
        if token_input and token_input.get("value"):
            token = token_input["value"]
            _LOGGER.debug("Found RequestVerificationToken in HTML input (length=%d)", len(token))
            return token

        # Secondary: some responses surface the token as a meta tag.
        token_meta = soup.find("meta", attrs={"name": "__RequestVerificationToken"})
        if token_meta and token_meta.get("content"):
            token = token_meta["content"]
            _LOGGER.debug("Found RequestVerificationToken in HTML meta (length=%d)", len(token))
            return token

        # Fallback: extract token from cookie header when dashboard HTML omits form.
        cookie_header = self.session.headers.get("Cookie", "")
        cookie_match = re.search(
            r"__RequestVerificationToken=([^;]+)",
            cookie_header,
        )
        if cookie_match:
            token = cookie_match.group(1).strip()
            _LOGGER.debug("Found RequestVerificationToken in cookie header (length=%d)", len(token))
            return token

        return None

    def _setup_chart_context(self, request_token: str, start_date: datetime, end_date: datetime) -> None:
        """Set up the Chart context with hourly granularity."""
        chart_setup_url = "https://mysmartenergy.nj.pseg.com/Dashboard/Chart"
        chart_setup_data = {
            "__RequestVerificationToken": request_token,
            "UsageInterval": "5",  # 5 = Hourly granularity
            "UsageType": "1",
            "jsTargetName": "StorageType",
            "EnableHoverChart": "true",
            "Start": start_date.strftime("%Y-%m-%d"),
            "End": end_date.strftime("%Y-%m-%d"),
            "IsRangeOpen": "False",
            "MaintainMaxDate": "true",
            "SelectedViaDateRange": "False",
            "ChartComparison": "1",
            "ChartComparison2": "0",
            "ChartComparison3": "0",
            "ChartComparison4": "0"
        }

        _LOGGER.debug("Chart setup: hourly, start=%s, end=%s",
                    start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

        chart_setup_response = self.session.post(
            chart_setup_url, data=chart_setup_data, timeout=REQUEST_TIMEOUT,
        )
        chart_setup_response.raise_for_status()

        try:
            chart_setup_json = json.loads(chart_setup_response.text)
            if "AjaxResults" in chart_setup_json and chart_setup_json["AjaxResults"]:
                for result in chart_setup_json["AjaxResults"]:
                    if result.get("Action") == "Redirect":
                        _LOGGER.error("Chart setup redirected to: %s", result.get('Value'))
                        raise InvalidAuth("Chart setup failed — hourly context not established")
        except json.JSONDecodeError:
            _LOGGER.error("Chart setup response is not JSON")
            raise InvalidAuth("Chart setup response is not JSON")

    def _get_chart_data(self) -> dict[str, Any]:
        """Get the actual chart data from PSEG."""
        chart_data_url = "https://mysmartenergy.nj.pseg.com/Dashboard/ChartData"
        chart_data_params = {
            "_": int(datetime.now().timestamp() * 1000)  # Cache buster
        }

        chart_response = self.session.get(
            chart_data_url, params=chart_data_params, timeout=REQUEST_TIMEOUT,
        )
        chart_response.raise_for_status()

        _LOGGER.debug("ChartData response status: %s", chart_response.status_code)

        chart_data = json.loads(chart_response.text)
        return chart_data

    def get_usage_data(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        days_back: int = 0,
    ) -> dict[str, Any]:
        """Get usage data from PSEG.

        If start_date and end_date are provided, they are used directly.
        Otherwise, dates are calculated from days_back.
        """
        try:
            # Use caller-provided dates if both are given
            if start_date is not None and end_date is not None:
                pass  # use as-is
            elif days_back == 0:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=1)
            else:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days_back)

            _LOGGER.debug("Date range: days_back=%d, start=%s, end=%s",
                        days_back, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

            # _get_dashboard_page checks for login redirect (auth gate)
            _, request_token = self._get_dashboard_page()
            self._setup_chart_context(request_token, start_date, end_date)
            chart_data = self._get_chart_data()

            widget_data = {"AjaxResults": []}
            return self._parse_data(widget_data, chart_data)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
            _LOGGER.error("Network error getting usage data: %s", err)
            raise PSEGLIError(f"Network error: {err}") from err
        except requests.exceptions.RequestException as err:
            _LOGGER.error("HTTP error getting usage data: %s", err)
            raise PSEGLIError(f"HTTP error: {err}") from err
        except json.JSONDecodeError as err:
            _LOGGER.error("Failed to parse JSON — likely expired cookie: %s", err)
            raise InvalidAuth("Cookie expired — server returned HTML instead of JSON") from err

    def _parse_data(self, widget_data: dict[str, Any], chart_data: dict[str, Any]) -> dict[str, Any]:
        """Parse the widget and chart data."""
        result = {
            "widgets": {},
            "chart_data": {},
            "last_update": datetime.now().isoformat()
        }

        # Parse widget data
        for result_item in widget_data.get("AjaxResults", []):
            if result_item.get("Action") == "Prepend" and "usageWidget" in result_item.get("Value", ""):
                html_content = result_item.get("Value", "")
                soup = BeautifulSoup(html_content, "html.parser")

                usage_widgets = soup.find_all("div", class_="usageWidget")
                for widget in usage_widgets:
                    usage_h2 = widget.find("h2")
                    if usage_h2:
                        usage_value = usage_h2.get_text(strip=True)

                        description_div = widget.find("div", class_="widgetDescription")
                        description = description_div.get_text(strip=True) if description_div else ""

                        range_alert = widget.find("div", class_="rangeAlert")
                        comparison = range_alert.get_text(strip=True) if range_alert else ""

                        try:
                            numeric_value = float(usage_value.replace("kWh", "").strip())
                        except ValueError:
                            numeric_value = 0.0

                        result["widgets"][description] = {
                            "value": numeric_value,
                            "raw_value": usage_value,
                            "description": description,
                            "comparison": comparison,
                        }

        # Parse chart data
        if "Data" in chart_data and "series" in chart_data["Data"]:
            for series in chart_data["Data"]["series"]:
                series_name = series.get("name", "Unknown")
                data_points = series.get("data", [])

                _LOGGER.debug("Processing series: %s with %d data points", series_name, len(data_points))

                eastern = pytz.timezone('America/New_York')
                valid_points = []
                for i, point in enumerate(data_points):
                    if isinstance(point, dict) and "x" in point and "y" in point:
                        timestamp = point["x"] / 1000
                        value = point["y"]
                        if value is None:
                            value = 0
                        # The API returns timestamps as Eastern local time encoded as
                        # Unix epoch (the epoch values represent local ET, not actual
                        # UTC). We extract the raw hour/minute values and localize them
                        # as America/New_York so DST is handled correctly.
                        utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                        naive_dt = utc_dt.replace(tzinfo=None)
                        local_time = eastern.localize(naive_dt)
                        valid_points.append({
                            "timestamp": local_time,
                            "value": value
                        })
                    elif isinstance(point, list) and len(point) >= 2:
                        # Array format: daily summaries, not hourly — skip
                        continue

                if valid_points:
                    latest_point = max(valid_points, key=lambda x: x["timestamp"])
                    values = [p["value"] for p in valid_points]

                    _LOGGER.debug("Series %s: %d valid points", series_name, len(valid_points))

                    result["chart_data"][series_name] = {
                        "latest_value": latest_point["value"],
                        "latest_timestamp": latest_point["timestamp"].isoformat(),
                        "min_value": min(values) if values else 0,
                        "max_value": max(values) if values else 0,
                        "avg_value": sum(values) / len(values) if values else 0,
                        "data_points": len(valid_points),
                        "valid_points": valid_points
                    }

        return result
