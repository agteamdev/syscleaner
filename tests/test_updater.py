import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from tests import helpers  # noqa: F401
from syscleaner import updater


def rel(tag, **kw):
    return dict({"tag_name": tag, "html_url": f"https://example.test/releases/{tag}", "draft": False,
                 "prerelease": False}, **kw)


class VersionTests(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(updater.parse_version("v0.4.0"), (0, 4, 0, 0))
        self.assertEqual(updater.parse_version("1.10"), (1, 10, 0, 0))
        self.assertTrue(updater.is_newer("0.10.0", "0.9.0"))       # numeric, not text order
        self.assertFalse(updater.is_newer("0.4.0", "0.4.0"))
        self.assertFalse(updater.is_newer("0.3.0", "0.4.0"))
        self.assertTrue(updater.is_newer("v0.4.1", "0.4.0"))
        self.assertTrue(updater.is_newer("1.0.0-rc1", "0.9.9"))


class CheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = {"code": 200, "body": [], "seen": {}}
        state = cls.state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(state["code"])
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(state["body"]).encode())
                state["seen"] = dict(self.headers)

            def log_message(self, *a):
                pass

        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/releases"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def check(self, body, code=200, current="0.4.0"):
        self.state.update(body=body, code=code)
        return updater.check(current, url=self.url)

    def test_newest_published_release_wins_and_drafts_are_ignored(self):
        r = self.check([rel("v0.5.0", prerelease=True), rel("v0.9.0", draft=True), rel("v0.4.1"), rel("v0.3.0")])
        self.assertTrue(r["ok"] and r["newer"])
        self.assertEqual(r["latest"], "0.4.1")
        self.assertTrue(r["url"].endswith("v0.4.1"))
        self.assertEqual(self.state["seen"].get("Accept"), "application/vnd.github+json")
        self.assertTrue(self.state["seen"].get("User-Agent", "").startswith("SysCleaner/"))

    def test_up_to_date(self):
        r = self.check([rel("v0.4.0"), rel("v0.3.0")])
        self.assertTrue(r["ok"] and not r["newer"])

    def test_no_releases_and_odd_json(self):
        self.assertIsNone(self.check([])["latest"])
        self.assertIsNone(self.check({"message": "weird"})["latest"])

    def test_http_errors_become_codes(self):
        self.assertEqual(self.check({}, code=403)["error"], "rate_limit")
        self.assertEqual(self.check({}, code=404)["error"], "http_404")

    def test_no_connection_never_raises(self):
        r = updater.check("0.4.0", url="http://127.0.0.1:9/nothing", timeout=2)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "offline")


if __name__ == "__main__":
    unittest.main()
