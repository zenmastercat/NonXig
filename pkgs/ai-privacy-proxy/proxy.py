"""ai-privacy-proxy: a local gateway between AI tools and their APIs.

Every request body an AI tool sends (Claude Code, Codex, ...) passes through
here. Secrets and personal terms are replaced by "[REDACTED:<kind>]" and the
rest is sent on unchanged; responses stream back untouched. Only the *kind* of
what was removed is logged, never the value.

Config: JSON file given as argv[1] (written by the NixOS module):
  listen_host, listen_port, routes {prefix: upstream_base},
  secret_globs [..], terms_file
"""

import asyncio
import glob
import gzip
import json
import os
import re
import sys
import time
import zlib
from collections import Counter

from aiohttp import ClientSession, ClientTimeout, TCPConnector, WSMsgType, web

try:  # Python >= 3.14
    from compression import zstd
except ImportError:  # pragma: no cover
    zstd = None

PLACEHOLDER = "[REDACTED:{}]"

# High-confidence formats only: a false match changes text the model needs.
PATTERNS = [
    ("private-key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S)),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openrouter-key", re.compile(r"\bsk-or-v1-[A-Fa-f0-9]{32,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{32,}")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("stripe-key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{20,}")),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{34,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
]

# user:password@ in URLs: only the password goes.
URL_CREDS = re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s/:@\"']+:)([^\s/@\"']{3,})(@)", re.I)

# password = "...", api_key: ..., etc. The value must look like a credential,
# not code or a path (so "token = mkOption {" and "passwordFile = /run/x" stay).
ASSIGN = re.compile(
    r"(?i)\b((?:[a-z0-9_]*[_\-])?(?:password|passwd|secret|api[_\-]?key|access[_\-]?token|"
    r"auth[_\-]?token|client[_\-]?secret|private[_\-]?key))\b(\"?'?\s*[:=]\s*[\"']?)"
    r"([^\s\"'`,;(){}\[\]<>$]{12,})")


def _looks_like_secret_value(v):
    return (not v.startswith(("/", "~", "./", "http", "REDACTED"))
            and any(c.isdigit() for c in v) and any(c.isalpha() for c in v))


SECRET_KEY_NAME = re.compile(r"(?i)token|secret|passw|api[_\-]?key|private[_\-]?key|^key$")


def _looks_like_token(v):
    """Values read from key files: only token-like strings, so settings such as
    timestamps, hosts, ports or "true" in the same files are not redacted."""
    return (len(v) >= 16 and not any(c.isspace() for c in v)
            and not re.match(r"^(\d{4}-\d\d-\d\d|https?://|/|~)", v)
            and any(c.isdigit() for c in v) and any(c.isalpha() for c in v)
            and len(set(v)) >= 10)


class Redactor:
    def __init__(self, secret_globs=(), terms_file=None):
        self.secret_globs = list(secret_globs)
        self.terms_file = terms_file
        self._stamp = None
        self._exact = None  # compiled alternation of known secret values
        self._terms = None
        self.reload(force=True)

    # -- known values from files ------------------------------------------
    def _files(self):
        out = []
        for g in self.secret_globs:
            out += [p for p in glob.glob(os.path.expanduser(g), recursive=True) if os.path.isfile(p)]
        return sorted(set(out))

    @staticmethod
    def _values_from(path):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read(1 << 20)
        except OSError:
            return []
        try:
            data = json.loads(text)
            vals = []

            # Only fields named like secrets: ids, scopes and plan names in the
            # same files are account metadata the API needs, not secrets.
            def walk(x, key=""):
                if isinstance(x, dict):
                    for k, v in x.items():
                        walk(v, str(k))
                elif isinstance(x, list):
                    for v in x:
                        walk(v, key)
                elif isinstance(x, str) and SECRET_KEY_NAME.search(key):
                    vals.append(x)
            walk(data)
            return vals
        except ValueError:
            pass
        lines = [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        if lines and all("=" in l for l in lines):
            return [l.split("=", 1)[1].strip().strip("\"'") for l in lines]
        return [text.strip()]

    def reload(self, force=False):
        files = self._files()
        tf = os.path.expanduser(self.terms_file) if self.terms_file else None
        stamp = tuple((p, os.stat(p).st_mtime_ns) for p in files + ([tf] if tf and os.path.isfile(tf) else []))
        if not force and stamp == self._stamp:
            return
        self._stamp = stamp
        self._source = {}  # value -> file name, so the log can say where a match came from
        for p in files:
            for v in self._values_from(p):
                if _looks_like_token(v):
                    self._source.setdefault(v, os.path.basename(p))
        self._exact = (re.compile("|".join(re.escape(v) for v in sorted(self._source, key=len, reverse=True)))
                       if self._source else None)
        terms = []
        if tf and os.path.isfile(tf):
            with open(tf, encoding="utf-8") as f:
                terms = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        self._terms = (re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.I)
                       if terms else None)

    # -- text ---------------------------------------------------------------
    def text(self, s, hits):
        if self._exact is not None:
            def known(m):
                hits["known-secret"] += 1
                hits["known-secret:" + self._source.get(m.group(0), "?")] += 1
                return PLACEHOLDER.format("known-secret")
            s = self._exact.sub(known, s)
        for kind, rx in PATTERNS:
            s, n = rx.subn(PLACEHOLDER.format(kind), s)
            hits[kind] += n
        s, n = URL_CREDS.subn(lambda m: m.group(1) + PLACEHOLDER.format("url-password") + m.group(3), s)
        hits["url-password"] += n

        def assign(m):
            if not _looks_like_secret_value(m.group(3)):
                return m.group(0)
            hits["assigned-secret"] += 1
            return m.group(1) + m.group(2) + PLACEHOLDER.format("assigned-secret")
        s = ASSIGN.sub(assign, s)
        if self._terms is not None:
            s, n = self._terms.subn(PLACEHOLDER.format("private-term"), s)
            hits["private-term"] += n
        return s

    # -- JSON ---------------------------------------------------------------
    # Signed or opaque fields: changing them breaks the API call (thinking
    # signatures, encrypted reasoning, base64 images/files, ids).
    SKIP_KEYS = frozenset({"signature", "data", "encrypted_content", "id", "tool_use_id",
                           "call_id", "model", "type", "role", "cache_control", "previous_response_id"})
    SKIP_TYPES = frozenset({"thinking", "redacted_thinking", "reasoning"})

    def json(self, x, hits):
        if isinstance(x, dict):
            if isinstance(x.get("type"), str) and x.get("type") in self.SKIP_TYPES:
                return x
            return {k: (v if k in self.SKIP_KEYS and not isinstance(v, (dict, list)) else self.json(v, hits))
                    for k, v in x.items()}
        if isinstance(x, list):
            return [self.json(v, hits) for v in x]
        if isinstance(x, str):
            return self.text(x, hits)
        return x

    def body(self, raw, content_type, hits):
        """Return the redacted body bytes. Raises ValueError for undecodable text."""
        if not raw:
            return raw
        ct = (content_type or "").lower()
        if "json" in ct or raw[:1] in (b"{", b"["):
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
            if data is not None:
                out = self.json(data, hits)
                if not sum(hits.values()):
                    return raw  # keep the exact bytes when nothing changed
                return json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode()
        if ct.startswith("text/") or "json" in ct or "x-www-form-urlencoded" in ct or not ct:
            try:
                s = raw.decode("utf-8")
            except UnicodeDecodeError:
                if not ct:
                    return raw  # binary without a type: nothing to scan
                raise
            new = self.text(s, hits)
            return raw if new == s else new.encode()
        return raw  # multipart and other binary uploads pass as they are


def decode_body(raw, encoding):
    enc = (encoding or "").lower().strip()
    if not enc or enc == "identity":
        return raw
    if enc == "gzip":
        return gzip.decompress(raw)
    if enc == "deflate":
        return zlib.decompress(raw)
    if enc == "zstd" and zstd is not None:
        return zstd.decompress(raw)
    raise ValueError(f"unsupported Content-Encoding {enc}")


def codex_login_headers(auth_file):
    """Codex leaves its login off the apps-connector request (ps/...) when its
    base URL is not chatgpt.com. Read it from Codex's own login file so that
    request still works. Returns {} when the file has no ChatGPT login."""
    try:
        with open(os.path.expanduser(auth_file)) as f:
            tokens = json.load(f).get("tokens") or {}
    except (OSError, ValueError):
        return {}
    if not tokens.get("access_token"):
        return {}
    out = {"Authorization": "Bearer " + tokens["access_token"]}
    if tokens.get("account_id"):
        out["ChatGPT-Account-Id"] = tokens["account_id"]
    return out


HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
       "trailers", "transfer-encoding", "upgrade", "host", "content-length", "content-encoding"}
WS_SKIP = HOP | {"sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions",
                 "sec-websocket-protocol", "sec-websocket-accept"}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def summary(hits):
    return ",".join(f"{k}={v}" for k, v in sorted(hits.items()) if v) or "none"


class Proxy:
    def __init__(self, cfg):
        self.routes = sorted(cfg["routes"].items(), key=lambda kv: len(kv[0]), reverse=True)
        self.redactor = Redactor(cfg.get("secret_globs", []), cfg.get("terms_file"))
        # Only these path prefixes get Codex's login, and only when the request
        # came without one; the upstream for them must be chatgpt.com.
        # Telemetry paths: answered here with 204, nothing is sent on.
        self.drop_prefixes = tuple(cfg.get("drop_prefixes", []))
        self.codex_auth_file = cfg.get("codex_auth_file")
        self.codex_auth_prefixes = tuple(cfg.get("codex_auth_prefixes", ["/backend-api/ps/"]))
        self.session = None

    def route(self, path):
        for prefix, upstream in self.routes:
            p = "/" + prefix.strip("/")
            if path == p or path.startswith(p + "/"):
                return upstream.rstrip("/") + path[len(p):]
        return None

    async def start(self, app):
        self.session = ClientSession(
            auto_decompress=False,
            timeout=ClientTimeout(total=None, sock_connect=30, sock_read=900),
            connector=TCPConnector(limit=64))

    async def stop(self, app):
        await self.session.close()

    async def handle(self, request):
        if any(seg in ("..", ".") for seg in request.path.split("/")):
            return web.Response(status=400, text="ai-privacy-proxy: dot segments are not allowed\n")
        if self.drop_prefixes and request.path.startswith(self.drop_prefixes):
            log(f"DROPPED {request.method} {request.path} (telemetry)")
            return web.Response(status=204)
        target = self.route(request.path)
        if target is None:
            return web.Response(status=404, text="ai-privacy-proxy: no route for this path\n")
        if request.query_string:
            target += "?" + request.query_string
        self.redactor.reload()
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await self.websocket(request, target)

        hits = Counter()
        raw = await request.read()
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
        # The response goes back as it came, so ask upstream only for encodings
        # the client accepts (aiohttp would otherwise add gzip/br on its own).
        headers.setdefault("Accept-Encoding", request.headers.get("accept-encoding", "identity"))
        if (self.codex_auth_file and request.path.startswith(self.codex_auth_prefixes)
                and target.startswith("https://chatgpt.com/")
                and not any(k.lower() == "authorization" for k in headers)):
            headers.update(codex_login_headers(self.codex_auth_file))
        try:
            body = self.redactor.body(decode_body(raw, request.headers.get("content-encoding")),
                                      request.content_type, hits)
        except Exception as e:  # cannot read it, so it does not leave unscanned
            log(f"BLOCKED {request.method} {request.path}: body not scannable ({e})")
            return web.json_response(
                {"type": "error", "error": {"type": "privacy_proxy_error",
                                            "message": f"ai-privacy-proxy could not scan the request: {e}"}},
                status=502)
        async with self.session.request(request.method, target, headers=headers, data=body or None,
                                        allow_redirects=False) as up:
            log(f"{request.method} {request.path} {up.status} bytes={len(raw)} redacted={summary(hits)}")
            resp = web.StreamResponse(status=up.status, reason=up.reason)
            for k, v in up.headers.items():
                if k.lower() not in HOP or k.lower() == "content-encoding":
                    resp.headers.add(k, v)
            await resp.prepare(request)
            async for chunk in up.content.iter_any():
                await resp.write(chunk)
            await resp.write_eof()
            return resp

    async def websocket(self, request, target):
        protos = [p.strip() for p in request.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
        headers = {k: v for k, v in request.headers.items() if k.lower() not in WS_SKIP}
        url = "ws" + target[len("http"):] if target.startswith("http") else target
        async with self.session.ws_connect(url, headers=headers, protocols=protos,
                                           max_msg_size=0, autoping=True) as up:
            down = web.WebSocketResponse(protocols=[up.protocol] if up.protocol else (),
                                         max_msg_size=0, autoping=True)
            await down.prepare(request)
            log(f"WS open {request.path}")

            async def client_to_up():
                async for m in down:
                    if m.type == WSMsgType.TEXT:
                        hits = Counter()
                        try:
                            data = json.loads(m.data)
                            out = self.redactor.json(data, hits)
                            text = m.data if not sum(hits.values()) else json.dumps(
                                out, ensure_ascii=False, separators=(",", ":"))
                        except ValueError:
                            text = self.redactor.text(m.data, hits)
                        if sum(hits.values()):
                            log(f"WS {request.path} redacted={summary(hits)}")
                        await up.send_str(text)
                    elif m.type == WSMsgType.BINARY:
                        await up.send_bytes(m.data)
                    else:
                        break
                await up.close()

            async def up_to_client():
                async for m in up:
                    if m.type == WSMsgType.TEXT:
                        await down.send_str(m.data)
                    elif m.type == WSMsgType.BINARY:
                        await down.send_bytes(m.data)
                    else:
                        break
                await down.close()

            await asyncio.gather(client_to_up(), up_to_client(), return_exceptions=True)
            log(f"WS close {request.path}")
            return down


# The proxy decodes request bodies itself (decode_body), so a body in an
# encoding it cannot read is refused instead of sent unscanned.
HANDLER_ARGS = {"auto_decompress": False}


def make_app(cfg):
    proxy = Proxy(cfg)
    app = web.Application(client_max_size=256 * 1024 * 1024)
    app.on_startup.append(proxy.start)
    app.on_cleanup.append(proxy.stop)
    app.router.add_route("*", "/{tail:.*}", proxy.handle)
    return app


async def serve(cfg):
    """Plain HTTP on listen_port; optional HTTPS on tls_port (Codex accepts only
    an HTTPS ChatGPT backend). Both bind to the loopback address only."""
    import ssl
    runner = web.AppRunner(make_app(cfg), access_log=None, **HANDLER_ARGS)
    await runner.setup()
    host = cfg.get("listen_host", "127.0.0.1")
    sites = [web.TCPSite(runner, host, int(cfg.get("listen_port", 18765)))]
    if cfg.get("tls_port"):
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(os.path.expanduser(cfg["tls_cert"]), os.path.expanduser(cfg["tls_key"]))
        sites.append(web.TCPSite(runner, host, int(cfg["tls_port"]), ssl_context=ctx))
    for site in sites:
        await site.start()
        log(f"listening on {site.name}")
    await asyncio.Event().wait()


def main():
    with open(sys.argv[1]) as f:
        cfg = json.load(f)
    asyncio.run(serve(cfg))


if __name__ == "__main__":
    main()
