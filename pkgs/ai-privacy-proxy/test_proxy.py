# Tests for proxy.py. All tokens below are made-up example data.
import gzip
import json
import os
import tempfile
import unittest
from collections import Counter

from aiohttp import ClientSession, WSMsgType, web
from aiohttp.test_utils import TestServer

import proxy

GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
ANT = "sk-ant-api03-" + "x7Y8z9" * 6
KNOWN = "Zq81mXw0Pv93Lk27Hd55"  # a value only found in a key file


def red(s, **kw):
    hits = Counter()
    return proxy.Redactor(**kw).text(s, hits), hits


class TextRules(unittest.TestCase):
    def test_token_formats(self):
        for tok, kind in [(GH, "github-token"), (ANT, "anthropic-key"),
                          ("AKIA" + "ABCDEFGHIJKLMNOP", "aws-access-key"),
                          ("sk-or-v1-" + "ab12" * 16, "openrouter-key"),
                          ("hf_" + "aB3" * 12, "huggingface-token")]:
            out, hits = red(f"use {tok} here")
            self.assertEqual(out, f"use [REDACTED:{kind}] here", kind)
            self.assertEqual(hits[kind], 1)

    def test_private_key_block(self):
        k = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk\n-----END OPENSSH PRIVATE KEY-----"
        self.assertEqual(red(f"x\n{k}\ny")[0], "x\n[REDACTED:private-key]\ny")

    def test_url_password_only(self):
        out, _ = red("git clone https://me:S3cretPass@github.com/a/b")
        self.assertEqual(out, "git clone https://me:[REDACTED:url-password]@github.com/a/b")

    def test_assignment_values(self):
        for s in ['password = "hunter2hunter2X9"', "db_password=hunter2hunter2X9",
                  '"api_key": "abc123def456ghi789"', "CLIENT_SECRET: hunter2hunter2X9"]:
            out, hits = red(s)
            self.assertIn("[REDACTED:assigned-secret]", out, s)
            self.assertNotIn("hunter2", out, s)
            self.assertNotIn("abc123", out, s)

    def test_code_and_paths_stay(self):
        for s in ["token = mkOption {", "passwordFile = /run/secrets/db",
                  "api_key = os.environ['KEY']", "secret: ${{ secrets.TOKEN }}",
                  "wheelNeedsPassword = true;", "home /home/lucas/Projects", "sk-learn is a package"]:
            self.assertEqual(red(s)[0], s, s)

    def test_known_secret_and_terms_from_files(self):
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/keys")
        with open(f"{d}/keys/K", "w") as f:
            f.write(KNOWN + "\n")
        with open(f"{d}/app.env", "w") as f:
            f.write(f"PORT=20128\nHOST=127.0.0.1:20128\nAPI_KEY={KNOWN}x\nFLAG=true\n")
        with open(f"{d}/auth.json", "w") as f:
            json.dump({"last_refresh": "2026-11-22T10:00:00Z", "accountUuid": "0f3c2b1a-9d8e-4f7a-b6c5-d4e3f2a1b0c9",
                       "tokens": {"refresh_token": "Rt" + KNOWN}}, f)
        with open(f"{d}/terms", "w") as f:
            f.write("# private\nperson@example.org\n")
        kw = dict(secret_globs=[f"{d}/keys/*", f"{d}/*.env", f"{d}/auth.json"], terms_file=f"{d}/terms")
        out, hits = red(f"k={KNOWN} e={KNOWN}x r=Rt{KNOWN} mail PERSON@example.org port 20128 "
                        f"host 127.0.0.1:20128 at 2026-11-22T10:00:00Z acct 0f3c2b1a-9d8e-4f7a-b6c5-d4e3f2a1b0c9", **kw)
        self.assertNotIn(KNOWN, out)
        self.assertNotIn("example.org", out)
        self.assertIn("port 20128 host 127.0.0.1:20128 at 2026-11-22T10:00:00Z acct 0f3c2b1a-9d8e-4f7a-b6c5-d4e3f2a1b0c9", out)
        self.assertEqual(hits["known-secret"], 3)
        self.assertEqual(hits["known-secret:K"] + hits["known-secret:app.env"] + hits["known-secret:auth.json"], 3)
        self.assertEqual(hits["private-term"], 1)

    def test_idempotent(self):
        once = red(f"a {GH} b")[0]
        self.assertEqual(red(once)[0], once)


class JsonRules(unittest.TestCase):
    def test_signed_and_opaque_fields_untouched(self):
        body = {"model": "m", "messages": [{"role": "assistant", "content": [
            {"type": "thinking", "thinking": f"saw {GH}", "signature": "sig"},
            {"type": "redacted_thinking", "data": f"{GH}"},
            {"type": "text", "text": f"token {GH}"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": GH}},
            {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": f"echo {GH}"}}]}]}
        hits = Counter()
        out = proxy.Redactor().json(body, hits)
        c = out["messages"][0]["content"]
        self.assertEqual(c[0], body["messages"][0]["content"][0])
        self.assertEqual(c[1], body["messages"][0]["content"][1])
        self.assertEqual(c[2]["text"], "token [REDACTED:github-token]")
        self.assertEqual(c[3]["source"]["data"], GH)
        self.assertEqual(c[4]["input"]["command"], "echo [REDACTED:github-token]")
        self.assertEqual(c[4]["id"], "toolu_1")
        self.assertEqual(hits["github-token"], 2)

    def test_unchanged_body_keeps_bytes(self):
        raw = b'{"a": 1,  "b": "plain"}'
        self.assertIs(proxy.Redactor().body(raw, "application/json", Counter()), raw)


class EndToEnd(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen = []

        async def messages(req):
            self.seen.append((dict(req.headers), await req.read()))
            r = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await r.prepare(req)
            for i in range(3):
                await r.write(f"data: chunk{i} {GH}\n\n".encode())
            await r.write_eof()
            return r

        async def ws(req):
            w = web.WebSocketResponse()
            await w.prepare(req)
            async for m in w:
                self.seen.append(({}, m.data.encode()))
                await w.send_str("echo:" + m.data)
                break
            await w.close()
            return w

        up = web.Application()
        up.router.add_post("/v1/messages", messages)
        up.router.add_get("/v1/ws", ws)
        self.up = TestServer(up)
        await self.up.start_server()
        base = str(self.up.make_url("")).rstrip("/")
        self.px = TestServer(proxy.make_app({"routes": {"anthropic": base},
                                             "drop_prefixes": ["/anthropic/v1/telemetry"]}))
        await self.px.start_server(**proxy.HANDLER_ARGS)
        self.s = ClientSession()

    async def asyncTearDown(self):
        await self.s.close()
        await self.px.close()
        await self.up.close()

    async def test_post_is_redacted_and_stream_passes(self):
        body = json.dumps({"messages": [{"role": "user", "content": f"key {ANT}"}]}).encode()
        async with self.s.post(self.px.make_url("/anthropic/v1/messages?beta=true"), data=body,
                               headers={"Content-Type": "application/json", "x-api-key": "AUTH-HEADER"}) as r:
            self.assertEqual(r.status, 200)
            text = await r.text()
        headers, sent = self.seen[0]
        self.assertNotIn(ANT.encode(), sent)
        self.assertIn(b"[REDACTED:anthropic-key]", sent)
        self.assertEqual(headers.get("x-api-key"), "AUTH-HEADER")  # auth goes through unchanged
        self.assertEqual(text.count("data: chunk"), 3)  # responses are not altered
        self.assertIn(GH, text)

    async def test_gzip_body_is_scanned(self):
        body = gzip.compress(json.dumps({"input": f"x {GH}"}).encode())
        async with self.s.post(self.px.make_url("/anthropic/v1/messages"), data=body,
                               headers={"Content-Type": "application/json", "Content-Encoding": "gzip"}) as r:
            self.assertEqual(r.status, 200)
            await r.read()
        headers, sent = self.seen[0]
        self.assertNotIn("Content-Encoding", headers)
        self.assertIn(b"[REDACTED:github-token]", sent)

    async def test_zstd_body_is_scanned(self):
        body = proxy.zstd.compress(json.dumps({"input": f"x {GH}"}).encode())
        async with self.s.post(self.px.make_url("/anthropic/v1/messages"), data=body,
                               headers={"Content-Type": "application/json", "Content-Encoding": "zstd"}) as r:
            self.assertEqual(r.status, 200)
            await r.read()
        self.assertIn(b"[REDACTED:github-token]", self.seen[0][1])

    async def test_unknown_encoding_is_blocked_not_leaked(self):
        async with self.s.post(self.px.make_url("/anthropic/v1/messages"), data=b"\x00\x01",
                               headers={"Content-Type": "application/json", "Content-Encoding": "br"}) as r:
            self.assertEqual(r.status, 502)
        self.assertEqual(self.seen, [])

    async def test_websocket_text_frames(self):
        async with self.s.ws_connect(self.px.make_url("/anthropic/v1/ws")) as w:
            await w.send_str(json.dumps({"type": "response.create", "input": f"t {GH}"}))
            m = await w.receive()
            self.assertEqual(m.type, WSMsgType.TEXT)
        self.assertNotIn(GH.encode(), self.seen[0][1])
        self.assertIn(b"[REDACTED:github-token]", self.seen[0][1])

    async def test_accept_encoding_is_the_clients(self):
        async with self.s.post(self.px.make_url("/anthropic/v1/messages"), data=b"{}",
                               headers={"Content-Type": "application/json", "Accept-Encoding": "identity"}) as r:
            await r.read()
        self.assertEqual(self.seen[0][0].get("Accept-Encoding"), "identity")

    async def test_codex_login_never_goes_to_other_hosts(self):
        d = tempfile.mkdtemp()
        with open(f"{d}/auth.json", "w") as f:
            json.dump({"tokens": {"access_token": "AT-example", "account_id": "acct-example"}}, f)
        self.assertEqual(proxy.codex_login_headers(f"{d}/auth.json"),
                         {"Authorization": "Bearer AT-example", "ChatGPT-Account-Id": "acct-example"})
        self.assertEqual(proxy.codex_login_headers(f"{d}/missing.json"), {})
        base = str(self.up.make_url("")).rstrip("/")
        px = TestServer(proxy.make_app({"routes": {"backend-api": base + "/v1"},
                                        "codex_auth_file": f"{d}/auth.json"}))
        await px.start_server(**proxy.HANDLER_ARGS)
        try:
            async with self.s.post(px.make_url("/backend-api/ps/../messages"), data=b"{}") as r:
                await r.read()
            async with self.s.post(px.make_url("/backend-api/messages"), data=b"{}") as r:
                await r.read()
        finally:
            await px.close()
        for headers, _ in self.seen:  # upstream here is not chatgpt.com
            self.assertNotIn("Authorization", headers)

    async def test_dot_segments_refused(self):
        from yarl import URL
        url = URL(str(self.px.make_url("")).rstrip("/") + "/anthropic/v1/../v1/messages", encoded=True)
        async with self.s.get(url) as r:
            self.assertEqual(r.status, 400)

    async def test_telemetry_dropped(self):
        async with self.s.post(self.px.make_url("/anthropic/v1/telemetry/events"), data=b"{}") as r:
            self.assertEqual(r.status, 204)
        self.assertEqual(self.seen, [])

    async def test_unknown_route_404(self):
        async with self.s.get(self.px.make_url("/nowhere")) as r:
            self.assertEqual(r.status, 404)


if __name__ == "__main__":
    unittest.main()
