import ast
import base64
import hashlib
import io
import json
import math
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import Mock
from urllib import error as urllib_error, request as urllib_request


class BmsTokenTests(unittest.TestCase):
    def setUp(self):
        # Load only auth helpers: importing the server starts runtime services.
        path = Path(__file__).resolve().parents[1] / "server" / "server.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name.startswith("_bms_")]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.http = Mock()
        self.scope = dict(globals(), _BMS_TOKEN_LOCK=threading.Lock(),
                          _BMS_TOKEN_CACHE={},
                          BMS_TOKEN_CACHE_FILE=Path(self.temp.name) / "token.json",
                          urllib_request=Mock(Request=urllib_request.Request, urlopen=self.http))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), self.scope)
        self.config = {"base_url": "https://example.invalid/v1", "username": "production",
                       "password": "test-password", "ttl_seconds": 604800,
                       "force_new_token": True}
        self.login = self.scope["_bms_login_token"]
        self.open = self.scope["_bms_open"]

    @staticmethod
    def response(token="token-one", **fields):
        return io.BytesIO(json.dumps({"data": {"token": token, **fields}}).encode())

    def test_concurrent_calls_and_restart_use_one_login(self):
        self.http.side_effect = lambda *a, **kw: self.response()
        with ThreadPoolExecutor(max_workers=12) as pool:
            tokens = list(pool.map(lambda _: self.login(self.config), range(40)))
        self.assertEqual(set(tokens), {"token-one"})
        self.assertEqual(self.http.call_count, 1)
        body = json.loads(self.http.call_args.args[0].data)
        self.assertFalse(body["forceNewToken"])
        self.scope["_BMS_TOKEN_CACHE"].clear()
        self.assertEqual(self.login(self.config), "token-one")
        self.assertEqual(self.http.call_count, 1)
        saved = self.scope["BMS_TOKEN_CACHE_FILE"].read_text()
        self.assertNotIn("test-password", saved)

    def test_expired_token_gets_replaced(self):
        self.http.side_effect = [self.response(expires_at="2000-01-01T00:00:00Z"),
                                 self.response("token-two")]
        self.login(self.config)
        self.assertEqual(self.login(self.config), "token-two")
        self.assertEqual(self.http.call_count, 2)

    def test_early_rejection_refreshes_and_retries_once(self):
        seen = []
        def upstream(req, **kwargs):
            if req.full_url.endswith("/auth/login"):
                seen.append(json.loads(req.data)["forceNewToken"])
                return self.response("new" if len(seen) == 2 else "old")
            if req.get_header("Authorization") == "Bearer old":
                raise urllib_error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO())
            return io.BytesIO(b'{"ok": true}')
        self.http.side_effect = upstream
        with self.open(self.config, urllib_request.Request("https://example.invalid/v1/jobs/1")) as resp:
            self.assertTrue(json.load(resp)["ok"])
        self.assertEqual(seen, [False, True])
        self.assertEqual(self.login(self.config, rejected_token="old"), "new")
        self.assertEqual(seen, [False, True])

    def test_simultaneous_rejections_refresh_only_once(self):
        self.http.side_effect = lambda *a, **kw: self.response("old")
        self.login(self.config)
        self.http.side_effect = lambda *a, **kw: self.response("new")
        with ThreadPoolExecutor(max_workers=12) as pool:
            tokens = list(pool.map(lambda _: self.login(self.config, rejected_token="old"), range(40)))
        self.assertEqual(set(tokens), {"new"})
        self.assertEqual(self.http.call_count, 2)

    def test_second_rejection_does_not_loop(self):
        self.http.side_effect = [self.response("old"),
            urllib_error.HTTPError("https://example.invalid", 401, "Unauthorized", {}, io.BytesIO()),
            self.response("new"),
            urllib_error.HTTPError("https://example.invalid", 401, "Unauthorized", {}, io.BytesIO())]
        with self.assertRaises(urllib_error.HTTPError):
            self.open(self.config, urllib_request.Request("https://example.invalid/v1/jobs/1"))
        self.assertEqual(self.http.call_count, 4)

    def test_json_unauthorized_response_refreshes_once(self):
        self.http.side_effect = [self.response("old"),
                                io.BytesIO(b'{"code":401,"message":"Unauthorized"}'),
                                self.response("new"), io.BytesIO(b'{"code":200}')]
        with self.open(self.config, urllib_request.Request("https://example.invalid/v1/jobs/1")) as response:
            self.assertEqual(json.load(response)["code"], 200)
        self.assertEqual(self.http.call_count, 4)

    def test_read_only_cache_directory_still_reuses_token(self):
        self.scope["BMS_TOKEN_CACHE_FILE"].write_text("file, not a directory")
        self.scope["BMS_TOKEN_CACHE_FILE"] /= "cache.json"
        self.http.side_effect = lambda *a, **kw: self.response()
        self.assertEqual(self.login(self.config), self.login(self.config))
        self.assertEqual(self.http.call_count, 1)

    def test_other_http_errors_do_not_refresh(self):
        for status in (403, 429, 500):
            with self.subTest(status=status):
                self.scope["_BMS_TOKEN_CACHE"].clear()
                self.scope["BMS_TOKEN_CACHE_FILE"].unlink(missing_ok=True)
                self.http.reset_mock()
                self.http.side_effect = [self.response(),
                    urllib_error.HTTPError("https://example.invalid", status, "error", {}, io.BytesIO())]
                with self.assertRaises(urllib_error.HTTPError):
                    self.open(self.config, urllib_request.Request("https://example.invalid/v1/jobs/1"))
                self.assertEqual(self.http.call_count, 2)

    def test_login_failure_does_not_retry_alternate_credentials(self):
        for error in (TimeoutError(), urllib_error.HTTPError("url", 401, "bad credentials", {}, io.BytesIO()),
                      urllib_error.HTTPError("url", 429, "rate limited", {}, io.BytesIO())):
            self.http.reset_mock()
            self.http.side_effect = error
            with self.assertRaises(type(error)):
                self.login(self.config)
            self.assertEqual(self.http.call_count, 1)

    def test_credential_change_and_corrupt_cache(self):
        self.scope["BMS_TOKEN_CACHE_FILE"].write_text("not json")
        self.http.side_effect = [self.response("one"), self.response("two")]
        self.assertEqual(self.login(self.config), "one")
        self.assertEqual(self.login(dict(self.config, password="changed")), "two")
        self.assertEqual(self.http.call_count, 2)

    def test_expiry_metadata_and_jwt_are_honored(self):
        expiry = self.scope["_bms_token_expiry"]
        jwt = "header." + base64.urlsafe_b64encode(b'{"exp": 1200}').decode().rstrip("=") + ".signature"
        self.assertEqual(expiry({}, jwt, 1000, 604800), 1200)
        self.assertEqual(expiry({"data": {"expires_in": 60}}, "opaque", 1000, 604800), 1060)
        self.assertEqual(expiry({}, "opaque", 1000, 604800), 605800)


if __name__ == "__main__":
    unittest.main()

