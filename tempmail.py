"""Tempik disposable-mail client (self-hosted instance).

Env:
  TEMPIK_BASE     e.g. https://mail.example.com/api
  TEMPIK_DOMAINS  optional comma list of domains to rotate
"""

from __future__ import annotations

import json
import os
import random
import re
import string
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

TEMPIK_BASE = (os.getenv("TEMPIK_BASE") or "").rstrip("/")
DEFAULT_DOMAINS = [d for d in (os.getenv("TEMPIK_DOMAINS") or "").split(",") if d]


class TempikClient:
    def __init__(self, base_url: Optional[str] = None):
        base = (base_url or TEMPIK_BASE or "").rstrip("/")
        if not base:
            raise ValueError("TEMPIK_BASE is not set (e.g. https://your-host/api)")
        self.base_url = base
        self.session_id: Optional[str] = None

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> Any:
        headers = {"User-Agent": UA, "Accept": "application/json"}
        if self.session_id:
            headers["x-session-id"] = self.session_id
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode()
        req = urllib.request.Request(f"{self.base_url}{path}", data=body,
                                     headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else None

    def init_session(self) -> str:
        if not self.session_id:
            self.session_id = (self._request("GET", "/session") or {}).get("sessionId")
        return self.session_id or ""

    def create_inbox(self, local_part: Optional[str] = None,
                     domain: Optional[str] = None) -> str:
        self.init_session()
        payload: Dict[str, Any] = {}
        if local_part:
            payload["name"] = local_part
        if domain or DEFAULT_DOMAINS:
            payload["domain"] = domain or random.choice(DEFAULT_DOMAINS)
        res = self._request("POST", "/inboxes", payload) or {}
        return res.get("address") or ""

    def get_messages(self, address: str) -> List[Dict[str, Any]]:
        self.init_session()
        try:
            res = self._request("GET", f"/inboxes/{address}/messages")
            return res if isinstance(res, list) else []
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise

    def get_message_detail(self, address: str, message_id: str) -> Dict[str, Any]:
        self.init_session()
        res = self._request("GET", f"/inboxes/{address}/messages/{message_id}")
        return res if isinstance(res, dict) else {}

    def wait_for_message(self, address: str, timeout: int = 90,
                         poll: int = 4) -> Optional[Dict[str, Any]]:
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            msgs = self.get_messages(address)
            if msgs:
                return msgs[0]
            time.sleep(poll)
        return None


def random_local(n: int = 9) -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(n))


def extract_code(text: str) -> Optional[str]:
    """Grab a 4-8 digit verification code from a subject or body."""
    if not text:
        return None
    m = re.search(r"\b(\d{6})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4,8})\b", text)
    return m.group(1) if m else None
