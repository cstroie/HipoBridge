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
    _text_to_report_html, _markdown_to_html, _dokuwiki_heading_to_bold,
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


class TestTextToReportHtml(unittest.TestCase):
    """_text_to_report_html() / _markdown_to_html() / _dokuwiki_heading_to_bold():
    the markdown/DokuWiki → HTML conversion posted to Hipocrate's literal-HTML
    Rezultate.asp field (see the docstrings for why <br> and bold-not-<h#>)."""

    def test_markdown_bold(self):
        self.assertEqual(_markdown_to_html('a **bold** word'), 'a <b>bold</b> word')

    def test_markdown_italic(self):
        self.assertEqual(_markdown_to_html('a *italic* word'), 'a <i>italic</i> word')

    def test_dokuwiki_italic(self):
        self.assertEqual(_markdown_to_html('a //italic// word'), 'a <i>italic</i> word')

    def test_dokuwiki_heading_to_bold(self):
        self.assertEqual(_dokuwiki_heading_to_bold('==== Findings ===='), '**Findings**')
        self.assertEqual(_dokuwiki_heading_to_bold('== Findings =='), '**Findings**')

    def test_dokuwiki_heading_ignores_non_heading_lines(self):
        self.assertEqual(_dokuwiki_heading_to_bold('plain text'), 'plain text')
        self.assertEqual(_dokuwiki_heading_to_bold('= not a heading ='), '= not a heading =')

    def test_text_to_report_html_end_to_end(self):
        text = 'First **bold**\nSecond //italic//\n==== Findings ===='
        expected = 'First <b>bold</b><br>Second <i>italic</i><br><b>Findings</b>'
        self.assertEqual(_text_to_report_html(text), expected)

    def test_text_to_report_html_empty(self):
        self.assertEqual(_text_to_report_html('   \n  '), '')


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

    def test_uncancel_posts_hdnaction_da(self):
        client = _client(HippoClientCererePerform)
        responses = [
            ('<form><input name="hdnAction" value=""></form>', None),  # GET cerere.asp
            ('OK', None),                                                # POST cerere.asp
        ]
        client.make_authenticated_request = AsyncMock(side_effect=responses)
        data = _run(client.uncancel("111"))
        self.assertEqual(data.get("status"), "success")
        method, form = client.make_authenticated_request.call_args_list[1].args[1:3]
        self.assertEqual(method, "POST")
        self.assertEqual(form.get("hdnAction"), "DA")

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


class _FakeResp:
    def __init__(self, text): self._t = text; self.status = 200
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class TestMainPageBounce(unittest.TestCase):
    """Hipocrate answering a GET with its main page must be retried once and,
    if it persists, reported as MAIN_PAGE_ERROR (HTTP 503) — never cached."""
    MAIN = '<html><head><title>HIPOCRATE - PAGINA PRINCIPALA</title></head></html>'
    GOOD = '<html><head><title>HIPOCRATE - Cerere laborator</title></head></html>'

    def _client(self, pages):
        from unittest.mock import MagicMock
        client = _client(HippoClientCererePerform)
        client.session = MagicMock()
        client.session.cookie_jar = None
        client.session.get = MagicMock(side_effect=[_FakeResp(p) for p in pages])
        client.handle_response_encoding = AsyncMock(side_effect=lambda r: r._t)
        client.login_if_needed = AsyncMock(return_value=True)
        client.cache_get = AsyncMock(return_value=None)
        client.cache_put = AsyncMock()
        return client

    def test_persistent_main_page_is_error_and_not_cached(self):
        from hippoclient import MAIN_PAGE_ERROR
        client = self._client([self.MAIN, self.MAIN])
        url = client.get_full_url("/PARA/NOM/Listare/cerere.asp?id=mainpage-test-1")
        html, err = _run(client.make_authenticated_request(url, "GET", None, "u", "p"))
        self.assertIsNone(html)
        self.assertEqual(err, MAIN_PAGE_ERROR)
        client.cache_put.assert_not_called()
        from hippoclient import HippoData
        d = HippoData(); d.set_error(err)
        self.assertEqual(web_json_response(d).status, 503)

    def test_main_page_then_good_page_is_cached(self):
        client = self._client([self.MAIN, self.GOOD])
        url = client.get_full_url("/PARA/NOM/Listare/cerere.asp?id=mainpage-test-2")
        html, err = _run(client.make_authenticated_request(url, "GET", None, "u", "p"))
        self.assertIsNone(err)
        self.assertIn("Cerere laborator", html)
        client.cache_put.assert_called_once()


if __name__ == "__main__":
    unittest.main()
