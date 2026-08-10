#!/usr/bin/env python3
"""Regression tests for the write-path HippoClient classes
(HippoClientReportWrite, HippoClientReportValidate, HippoClientCererePerform).

Guards against the bug where every failure branch called
`data.store("message", ...)` instead of `data.set_error(...)`, leaving
`status` unset — which hippobridge.py's web_json_response() then mapped to
HTTP 200 (the same code path used for real successes), so a failed report
write / validate / perform / cancel came back to the browser looking like
a success.

Plain (synchronous) unittest.TestCase, not IsolatedAsyncioTestCase: this
suite's runner (runtests.py) drives everything through its own single
asyncio.run() call, and IsolatedAsyncioTestCase tries to start a second
event loop in the same thread, which asyncio forbids. _run() below runs
each coroutine to completion in a throwaway thread instead, so it composes
with runtests.py exactly like every other synchronous TestCase here
(TestHippoData, TestMarkdownConversion, ...)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

from hippoclient import (
    HippoClientReportWrite, HippoClientReportValidate, HippoClientCererePerform,
)
from hippobridge import web_json_response


def _run(coro):
    """Run coro to completion on a fresh event loop in a separate thread."""
    with ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


def _client(cls):
    c = cls("http://test.invalid", None)
    c.set_credentials("user", "pass")
    c.session = object()  # bypass get_user_session(); never dereferenced once make_authenticated_request is mocked
    return c


class TestReportWriteErrors(unittest.TestCase):
    def test_rezultate_get_failure_sets_error_status(self):
        client = _client(HippoClientReportWrite)
        client.make_authenticated_request = AsyncMock(return_value=(None, "connection refused"))
        data = _run(client.write("111", "222", "some report text"))
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("message"), "connection refused")

    def test_rezultate_get_empty_response_sets_error_status(self):
        client = _client(HippoClientReportWrite)
        client.make_authenticated_request = AsyncMock(return_value=("", None))
        data = _run(client.write("111", "222", "some report text"))
        self.assertEqual(data.get("status"), "error")
        self.assertIn("Empty response", data.get("message"))

    def test_missing_result_field_sets_error_status(self):
        client = _client(HippoClientReportWrite)
        client.make_authenticated_request = AsyncMock(return_value=("<html><body>no form here</body></html>", None))
        data = _run(client.write("111", "222", "some report text"))
        self.assertEqual(data.get("status"), "error")
        self.assertIn("Could not locate result field", data.get("message"))

    def test_post_failure_sets_error_status(self):
        client = _client(HippoClientReportWrite)
        responses = [
            ('<textarea name="v3760"></textarea>', None),  # GET Rezultate.asp
            (None, "POST timed out"),                        # POST Rezultate.asp
        ]
        client.make_authenticated_request = AsyncMock(side_effect=responses)
        data = _run(client.write("111", "222", "some report text"))
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("message"), "POST timed out")

    def test_happy_path_sets_success_status(self):
        client = _client(HippoClientReportWrite)
        responses = [
            ('<textarea name="v3760"></textarea>', None),  # GET Rezultate.asp
            ('OK', None),                                    # POST Rezultate.asp
        ]
        client.make_authenticated_request = AsyncMock(side_effect=responses)
        data = _run(client.write("111", "222", "some report text"))
        self.assertEqual(data.get("status"), "success")
        self.assertIsNone(data.get("message"))


class TestReportValidateErrors(unittest.TestCase):
    def test_request_failure_sets_error_status(self):
        client = _client(HippoClientReportValidate)
        client.make_authenticated_request = AsyncMock(return_value=(None, "connection refused"))
        data = _run(client.validate("111", "222", "0", True))
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("message"), "connection refused")

    def test_server_side_rejection_text_sets_error_status(self):
        # Ajax_Cerere.asp returns a non-empty body on failure (e.g. a
        # Romanian error message from Hipocrate itself) — an empty body is
        # the only actual success signal.
        client = _client(HippoClientReportValidate)
        client.make_authenticated_request = AsyncMock(return_value=("Eroare: cerere deja validata", None))
        data = _run(client.validate("111", "222", "0", True))
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("message"), "Eroare: cerere deja validata")

    def test_happy_path_sets_success_status(self):
        client = _client(HippoClientReportValidate)
        client.make_authenticated_request = AsyncMock(return_value=("", None))
        data = _run(client.validate("111", "222", "0", True))
        self.assertEqual(data.get("status"), "success")


class TestCererePerformErrors(unittest.TestCase):
    def test_cerere_get_failure_sets_error_status(self):
        client = _client(HippoClientCererePerform)
        client.make_authenticated_request = AsyncMock(return_value=(None, "connection refused"))
        data = _run(client.perform("111"))
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("message"), "connection refused")

    def test_no_form_found_sets_error_status(self):
        client = _client(HippoClientCererePerform)
        client.make_authenticated_request = AsyncMock(return_value=("<html><body>no form</body></html>", None))
        data = _run(client.perform("111"))
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("message"), "No form found in cerere.asp")

    def test_post_failure_sets_error_status_for_cancel_too(self):
        client = _client(HippoClientCererePerform)
        responses = [
            ('<form><input name="hdnAction" value=""></form>', None),  # GET cerere.asp
            (None, "POST failed"),                                       # POST cerere.asp
        ]
        client.make_authenticated_request = AsyncMock(side_effect=responses)
        data = _run(client.cancel("111"))
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("message"), "POST failed")

    def test_happy_path_sets_success_status(self):
        client = _client(HippoClientCererePerform)
        responses = [
            ('<form><input name="hdnAction" value=""></form>', None),  # GET cerere.asp
            ('OK', None),                                                # POST cerere.asp
        ]
        client.make_authenticated_request = AsyncMock(side_effect=responses)
        data = _run(client.perform("111"))
        self.assertEqual(data.get("status"), "success")


class TestWebJsonResponseEndToEnd(unittest.TestCase):
    """Closes the loop: a failed write must not just carry status='error'
    internally, it must actually produce a non-200 HTTP response through
    the same web_json_response() the routes use — that mapping is what a
    frontend gate on `resp.ok` actually observes."""

    def test_failed_perform_is_not_http_200(self):
        client = _client(HippoClientCererePerform)
        client.make_authenticated_request = AsyncMock(return_value=(None, "connection refused"))
        data = _run(client.perform("111"))
        resp = web_json_response(data)
        self.assertNotEqual(resp.status, 200)

    def test_failed_report_write_is_not_http_200(self):
        client = _client(HippoClientReportWrite)
        client.make_authenticated_request = AsyncMock(return_value=(None, "connection refused"))
        data = _run(client.write("111", "222", "text"))
        resp = web_json_response(data)
        self.assertNotEqual(resp.status, 200)

    def test_failed_validate_is_not_http_200(self):
        client = _client(HippoClientReportValidate)
        client.make_authenticated_request = AsyncMock(return_value=(None, "connection refused"))
        data = _run(client.validate("111", "222", "0", True))
        resp = web_json_response(data)
        self.assertNotEqual(resp.status, 200)

    def test_successful_perform_is_http_200(self):
        client = _client(HippoClientCererePerform)
        responses = [
            ('<form><input name="hdnAction" value=""></form>', None),
            ('OK', None),
        ]
        client.make_authenticated_request = AsyncMock(side_effect=responses)
        data = _run(client.perform("111"))
        resp = web_json_response(data)
        self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
