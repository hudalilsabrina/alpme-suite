"""Alpme (alpme.com) API client.

Signup is email+password only (no captcha, no email verification).
Key creation is gated behind `X-Alpme-Client: vscode` — without that header the
API answers 403 {"code":"desktop_only"}.

Base URL for inference: https://alpme.com/v1
"""

from __future__ import annotations

import json
import random
import string
import time
import urllib.error
import urllib.request
import http.cookiejar
from typing import Any, Dict, List, Optional

WEB = "https://alpme.com"
API = f"{WEB}/api"
INFER = f"{WEB}/v1"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

# The magic header that unlocks POST /api/keys.
DESKTOP_HEADER = {"X-Alpme-Client": "vscode"}


class AlpmeError(Exception):
    def __init__(self, message: str, status: int = 0, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


def rand_password(n: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(random.choice(alphabet) for _ in range(n - 4))
    return core + random.choice("!@#$%") + random.choice(string.digits)


def rand_name() -> str:
    first = random.choice(
        ["Adi", "Budi", "Citra", "Dewi", "Eko", "Fajar", "Gita", "Hendra",
         "Indra", "Joko", "Kartika", "Lestari", "Made", "Nadia", "Oka",
         "Putri", "Raka", "Sari", "Teguh", "Wulan"]
    )
    last = random.choice(
        ["Pratama", "Santoso", "Wijaya", "Halim", "Nugroho", "Saputra",
         "Hartono", "Kusuma", "Maulana", "Setiawan", "Permana", "Anggraini"]
    )
    return f"{first} {last}"


class AlpmeClient:
    """One client == one browser session (cookie jar) == one account."""

    def __init__(self, timeout: int = 45, proxy: Optional[str] = None):
        self.timeout = timeout
        self.proxy = proxy
        self.jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.jar)]
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        self.opener = urllib.request.build_opener(*handlers)
        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.name: Optional[str] = None
        self.plan: Optional[Dict[str, Any]] = None

    def _bare_opener(self):
        if self.proxy:
            return urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
            )
        return urllib.request.build_opener()

    # ------------------------------------------------------------------ http
    def _request(
        self,
        method: str,
        url: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
        use_cookies: bool = True,
    ) -> Any:
        h = {"User-Agent": UA, "Accept": "application/json"}
        h.update(headers or {})
        data = None
        if payload is not None:
            h["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()

        req = urllib.request.Request(url, data=data, headers=h, method=method)
        opener = self.opener if use_cookies else urllib.request.build_opener()
        try:
            resp = opener.open(req, timeout=self.timeout)
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            code = ""
            try:
                code = (json.loads(raw) or {}).get("code", "") or ""
            except Exception:
                pass
            raise AlpmeError(raw[:300] or f"HTTP {e.code}", e.code, code)
        except Exception as e:  # transport
            raise AlpmeError(f"{type(e).__name__}: {e}")

    def _web_post(self, path: str, payload: dict, extra: Optional[dict] = None) -> Any:
        h = {"Origin": WEB, "Referer": f"{WEB}/signup"}
        h.update(extra or {})
        return self._request("POST", f"{API}{path}", payload, h)

    # ------------------------------------------------------------------ auth
    def signup(
        self,
        email: str,
        password: Optional[str] = None,
        name: Optional[str] = None,
        ref: str = "",
        promo: str = "",
    ) -> Dict[str, Any]:
        self.email = email
        self.password = password or rand_password()
        self.name = name or rand_name()
        res = self._web_post(
            "/auth/signup",
            {
                "email": self.email,
                "password": self.password,
                "name": self.name,
                "ref": ref,
                "promo": promo,
                "captcha": "",
            },
        )
        promo_info = (res or {}).get("promo") or {}
        if promo_info:
            self.plan = promo_info
        return res or {}

    def login(self, email: str, password: str) -> Dict[str, Any]:
        self.email = email
        self.password = password
        return self._web_post("/auth/login", {"email": email, "password": password}) or {}

    # ------------------------------------------------------------------ keys
    def list_keys(self) -> Dict[str, Any]:
        return self._request("GET", f"{API}/keys", None, DESKTOP_HEADER) or {}

    def create_key(self, name: str = "alp") -> str:
        """Mint an API key. Returns the plaintext `sk_live_*` secret."""
        res = self._web_post("/keys", {"name": name}, DESKTOP_HEADER) or {}
        secret = res.get("secret") or ""
        if not secret:
            raise AlpmeError(f"no secret in response: {str(res)[:200]}")
        if res.get("quota", {}).get("plan"):
            self.plan = res["quota"]["plan"]
        return secret

    def quota(self) -> Dict[str, Any]:
        return (self.list_keys() or {}).get("quota", {})

    # --------------------------------------------------------------- infer
    @staticmethod
    def models(api_key: str, timeout: int = 40) -> List[str]:
        req = urllib.request.Request(
            f"{INFER}/models",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": UA,
                     "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read().decode())
        return [m["id"] for m in d.get("data", [])]

    @staticmethod
    def chat(
        api_key: str,
        model: str,
        messages: List[dict],
        max_tokens: int = 512,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        body = json.dumps(
            {"model": model, "messages": messages, "max_tokens": max_tokens}
        ).encode()
        req = urllib.request.Request(
            f"{INFER}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": UA,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            code = ""
            try:
                code = ((json.loads(raw) or {}).get("error") or {}).get("code", "")
            except Exception:
                pass
            raise AlpmeError(raw[:300], e.code, code)
