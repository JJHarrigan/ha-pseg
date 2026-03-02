"""Tests for PSEGLIClient (mocked requests)."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from custom_components.psegli.psegli import PSEGLIClient, REQUEST_TIMEOUT
from custom_components.psegli.exceptions import InvalidAuth, PSEGLIError


class TestPSEGLIClient:
    """Tests for PSEGLIClient."""

    def test_no_thread_pool_executor_usage(self):
        """Verify no ThreadPoolExecutor in psegli.py."""
        import inspect
        from custom_components.psegli import psegli
        source = inspect.getsource(psegli)
        assert "ThreadPoolExecutor" not in source
        assert "get_event_loop" not in source

    def test_requests_have_timeouts(self):
        """Verify all requests calls include timeout."""
        import inspect
        from custom_components.psegli import psegli
        source = inspect.getsource(psegli)
        # Count session.get and session.post calls — each should have timeout
        import re
        gets = re.findall(r'self\.session\.get\(', source)
        posts = re.findall(r'self\.session\.post\(', source)
        timeouts = re.findall(r'timeout=REQUEST_TIMEOUT', source)
        # Each get/post should have a corresponding timeout
        assert len(timeouts) >= len(gets) + len(posts)

    def test_network_error_raises_psegli_error(self, mock_requests_session):
        """ConnectionError should raise PSEGLIError, not InvalidAuth."""
        mock_requests_session.get.side_effect = requests.exceptions.ConnectionError("DNS failed")

        with patch("custom_components.psegli.psegli.requests.Session", return_value=mock_requests_session):
            client = PSEGLIClient("MM_SID=test")
            client.session = mock_requests_session
            with pytest.raises(PSEGLIError):
                client.test_connection()

    def test_timeout_raises_psegli_error(self, mock_requests_session):
        """Timeout should raise PSEGLIError, not InvalidAuth."""
        mock_requests_session.get.side_effect = requests.exceptions.Timeout("timed out")

        client = PSEGLIClient("MM_SID=test")
        client.session = mock_requests_session
        with pytest.raises(PSEGLIError):
            client.test_connection()

    def test_auth_failure_raises_invalid_auth(self, mock_requests_session):
        """Redirect to login URL should raise InvalidAuth."""
        response = MagicMock()
        response.status_code = 200
        response.url = "https://mysmartenergy.psegliny.com/Login"
        response.raise_for_status = MagicMock()
        mock_requests_session.get.return_value = response

        client = PSEGLIClient("MM_SID=expired")
        client.session = mock_requests_session
        with pytest.raises(InvalidAuth):
            client.test_connection()

    def test_successful_connection(self, mock_requests_session):
        """Successful connection returns True."""
        response = MagicMock()
        response.status_code = 200
        response.url = "https://mysmartenergy.psegliny.com/Dashboard"
        response.raise_for_status = MagicMock()
        mock_requests_session.get.return_value = response

        client = PSEGLIClient("MM_SID=valid")
        client.session = mock_requests_session
        assert client.test_connection() is True

    def test_data_path_probe_successful(self, mock_requests_session):
        """Data-path probe should succeed when dashboard and chart setup succeed."""
        dashboard_response = MagicMock()
        dashboard_response.status_code = 200
        dashboard_response.url = "https://mysmartenergy.psegliny.com/Dashboard"
        dashboard_response.text = (
            '<input name="__RequestVerificationToken" type="hidden" value="token123" />'
        )
        dashboard_response.raise_for_status = MagicMock()
        mock_requests_session.get.return_value = dashboard_response

        chart_setup_response = MagicMock()
        chart_setup_response.raise_for_status = MagicMock()
        chart_setup_response.text = json.dumps({"AjaxResults": []})
        mock_requests_session.post.return_value = chart_setup_response

        client = PSEGLIClient("MM_SID=valid")
        client.session = mock_requests_session

        assert client.test_data_path() is True
        mock_requests_session.post.assert_called_once()

    def test_data_path_probe_does_not_fetch_chart_data(self, mock_requests_session):
        """Probe must validate only dashboard -> chart setup and skip ChartData."""
        dashboard_response = MagicMock()
        dashboard_response.status_code = 200
        dashboard_response.url = "https://mysmartenergy.psegliny.com/Dashboard"
        dashboard_response.text = (
            '<input name="__RequestVerificationToken" type="hidden" value="token123" />'
        )
        dashboard_response.raise_for_status = MagicMock()
        mock_requests_session.get.return_value = dashboard_response

        chart_setup_response = MagicMock()
        chart_setup_response.raise_for_status = MagicMock()
        chart_setup_response.text = json.dumps({"AjaxResults": []})
        mock_requests_session.post.return_value = chart_setup_response

        client = PSEGLIClient("MM_SID=valid")
        client.session = mock_requests_session

        with patch.object(client, "_get_chart_data", side_effect=AssertionError("should not fetch")) as mock_chart:
            assert client.test_data_path() is True
            mock_chart.assert_not_called()

    def test_data_path_probe_chart_redirect_raises_invalid_auth(self, mock_requests_session):
        """Chart setup redirect is an auth failure, not a transient error."""
        dashboard_response = MagicMock()
        dashboard_response.status_code = 200
        dashboard_response.url = "https://mysmartenergy.psegliny.com/Dashboard"
        dashboard_response.text = (
            '<input name="__RequestVerificationToken" type="hidden" value="token123" />'
        )
        dashboard_response.raise_for_status = MagicMock()
        mock_requests_session.get.return_value = dashboard_response

        chart_setup_response = MagicMock()
        chart_setup_response.raise_for_status = MagicMock()
        chart_setup_response.text = json.dumps(
            {"AjaxResults": [{"Action": "Redirect", "Value": "/"}]}
        )
        mock_requests_session.post.return_value = chart_setup_response

        client = PSEGLIClient("MM_SID=valid")
        client.session = mock_requests_session

        with pytest.raises(InvalidAuth):
            client.test_data_path()

    def test_data_path_probe_chart_http_error_raises_psegli_error(self, mock_requests_session):
        """Chart setup HTTP/5xx path should map to transient PSEGLIError."""
        dashboard_response = MagicMock()
        dashboard_response.status_code = 200
        dashboard_response.url = "https://mysmartenergy.psegliny.com/Dashboard"
        dashboard_response.text = (
            '<input name="__RequestVerificationToken" type="hidden" value="token123" />'
        )
        dashboard_response.raise_for_status = MagicMock()
        mock_requests_session.get.return_value = dashboard_response

        chart_setup_response = MagicMock()
        chart_setup_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "503 Server Error"
        )
        mock_requests_session.post.return_value = chart_setup_response

        client = PSEGLIClient("MM_SID=valid")
        client.session = mock_requests_session

        with pytest.raises(PSEGLIError):
            client.test_data_path()

    def test_data_path_probe_chart_transport_error_raises_psegli_error(self, mock_requests_session):
        """Chart setup transport failures should map to transient PSEGLIError."""
        dashboard_response = MagicMock()
        dashboard_response.status_code = 200
        dashboard_response.url = "https://mysmartenergy.psegliny.com/Dashboard"
        dashboard_response.text = (
            '<input name="__RequestVerificationToken" type="hidden" value="token123" />'
        )
        dashboard_response.raise_for_status = MagicMock()
        mock_requests_session.get.return_value = dashboard_response
        mock_requests_session.post.side_effect = requests.exceptions.ConnectionError(
            "connection reset"
        )

        client = PSEGLIClient("MM_SID=valid")
        client.session = mock_requests_session

        with pytest.raises(PSEGLIError):
            client.test_data_path()

    def test_explicit_dates_respected(self, mock_requests_session):
        """Caller-provided start_date and end_date should be used directly."""
        # Set up mock responses for the full get_usage_data flow
        dashboard_html = '<input name="__RequestVerificationToken" type="hidden" value="token123" />'
        chart_setup_json = json.dumps({"AjaxResults": []})
        chart_data_json = json.dumps({"Data": {"series": []}})

        responses = [
            # _get_dashboard_page GET (also serves as auth gate)
            MagicMock(status_code=200, url="https://mysmartenergy.psegliny.com/Dashboard",
                     text=dashboard_html, raise_for_status=MagicMock()),
            # _get_chart_data GET
            MagicMock(status_code=200, text=chart_data_json, raise_for_status=MagicMock()),
        ]
        mock_requests_session.get.side_effect = responses
        # _setup_chart_context POST
        mock_requests_session.post.return_value = MagicMock(
            status_code=200, text=chart_setup_json, raise_for_status=MagicMock()
        )

        client = PSEGLIClient("MM_SID=test")
        client.session = mock_requests_session

        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 15)
        client.get_usage_data(start_date=start, end_date=end)

        # Verify the dates were passed to _setup_chart_context via the POST
        post_call = mock_requests_session.post.call_args
        post_data = post_call.kwargs.get("data") or post_call[1].get("data")
        assert post_data["Start"] == "2026-01-01"
        assert post_data["End"] == "2026-01-15"

    def test_update_cookie(self):
        """update_cookie changes the session header."""
        client = PSEGLIClient("MM_SID=old")
        client.update_cookie("MM_SID=new_cookie_value")
        assert client.cookie == "MM_SID=new_cookie_value"

    def test_dashboard_token_extraction_tolerates_attribute_order(self, mock_requests_session):
        """Token extraction should not depend on exact input attribute order."""
        response = MagicMock()
        response.status_code = 200
        response.url = "https://mysmartenergy.psegliny.com/Dashboard"
        response.text = "<input value='token_reordered' id='x' type='hidden' name='__RequestVerificationToken' />"
        mock_requests_session.get.return_value = response

        client = PSEGLIClient("MM_SID=valid")
        client.session = mock_requests_session
        _, token = client._get_dashboard_page()

        assert token == "token_reordered"

    def test_dashboard_token_falls_back_to_cookie_when_input_missing(self, mock_requests_session):
        """If dashboard omits hidden input, fallback to token present in cookie header."""
        response = MagicMock()
        response.status_code = 200
        response.url = "https://mysmartenergy.psegliny.com/Dashboard"
        response.text = "<html><body><h1>Dashboard</h1></body></html>"
        mock_requests_session.get.return_value = response

        client = PSEGLIClient(
            "MM_SID=valid_sid; __RequestVerificationToken=token_from_cookie"
        )
        client.session = mock_requests_session
        client.session.headers = {
            "Cookie": "MM_SID=valid_sid; __RequestVerificationToken=token_from_cookie"
        }
        _, token = client._get_dashboard_page()

        assert token == "token_from_cookie"
