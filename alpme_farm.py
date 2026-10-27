#!/usr/bin/env python3
"""Alpme bulk registrar.

Flow per account (no captcha, no email verification):
    tempik inbox -> POST /api/auth/signup (ref + promo) -> login
    -> POST /api/keys  (X-Alpme-Client: vscode)  -> sk_live_* secret
    -> append to accounts.txt / keys.txt -> optionally inject into 9router

Usage:
    python3 alpme_farm.py -n 20 --gap 3
    python3 alpme_farm.py -n 5 --promo ALP27 --ref ariqnetz7-3b6e
    python3 alpme_farm.py -n 5 --no-9router
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpme_client import AlpmeClient, AlpmeError, rand_password, rand_name
from tempmail import TempikClient, random_local

ROOT = Path(__file__).resolve().parent
ACCOUNTS = ROOT / "accounts.txt"
KEYS = ROOT / "keys.txt"
LOG = ROOT / "farm.log"

DEFAULT_REF = os.getenv("ALPME_REF", "ariqnetz7-3b6e")
DEFAULT_PROMO = os.getenv("ALPME_PROMO", "ALP27")

N9_DB = os.getenv("N9_DB", "/var/lib/9router/db/data.sqlite")
N9_NODE_ID = "openai-compatible-chat-alpme"
N9_PROVIDER = "openai-compatible-chat-alpme"
N9_PREFIX = "alpme"
N9_BASE_URL = "https://alpme.com/v1"

TRANSIENT = ("timeout", "timed out", "handshake", "Broken pipe", "Connection",
             "URLError", "ssl", "SSL", "RemoteDisconnected", "reset by peer")


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def append(path: Path, line: str) -> None:
    with path.open("a") as f:
        f.write(line + "\n")


BRIDGE = os.getenv("ALPME_PROXY", "http://127.0.0.1:10801")


def rotate_ip() -> str:
    """Ask the residential bridge for a fresh exit IP. Returns the new IP."""
    try:
        req = urllib.request.Request(f"{BRIDGE}/__new_session", method="POST")
        urllib.request.urlopen(req, timeout=20).read()
    except Exception:
        pass
    try:
        op = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": BRIDGE, "https": BRIDGE})
        )
        return op.open("https://api.ipify.org", timeout=25).read().decode().strip()
    except Exception:
        return "?"


def ensure_node() -> None:
    """Register the alpme node in 9router once."""
    conn = sqlite3.connect(N9_DB, timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000")
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM providerNodes WHERE id=?", (N9_NODE_ID,)).fetchone()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    data = {
        "id": N9_NODE_ID,
        "type": "openai-compatible",
        "name": "Alpme",
        "prefix": N9_PREFIX,
        "baseUrl": N9_BASE_URL,
        "apiType": "chat",
        "isActive": True,
        "createdAt": now,
        "updatedAt": now,
        "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/133.0.0.0 Safari/537.36"},
    }
    if row:
        cur.execute("UPDATE providerNodes SET data=? WHERE id=?", (json.dumps(data), N9_NODE_ID))
    else:
        cur.execute(
            "INSERT INTO providerNodes (id, type, name, data, createdAt, updatedAt) "
            "VALUES (?,?,?,?,?,?)",
            (N9_NODE_ID, "openai-compatible", "Alpme", json.dumps(data), now, now),
        )
    conn.commit()
    conn.close()


def _connect(retries: int = 8):
    last = None
    for i in range(retries):
        try:
            conn = sqlite3.connect(N9_DB, timeout=60.0)
            conn.execute("PRAGMA busy_timeout=60000")
            conn.execute("SELECT 1 FROM apiKeys LIMIT 1").fetchone()
            return conn
        except sqlite3.OperationalError as e:
            last = e
            time.sleep(3 + i * 2)
    raise last


def inject_key(email: str, api_key: str) -> bool:
    try:
        ensure_node()
        conn = _connect()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        cid = f"alpme-{email.split('@')[0]}-{int(time.time()*1000)%100000}"
        data = {
            "id": cid,
            "provider": N9_PROVIDER,
            "name": email,
            "email": email,
            "apiKey": api_key,
            "baseUrl": N9_BASE_URL,
            "isActive": True,
            "testStatus": "active",
            "createdAt": now,
            "updatedAt": now,
        }
        cur.execute(
            "INSERT OR REPLACE INTO providerConnections "
            "(id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, N9_PROVIDER, "apikey", email, email, 1, 1, json.dumps(data), now, now),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log(f"  9router inject failed: {type(e).__name__}: {e}")
        return False


def register_one(promo: str, ref: str, idx: int, proxy: str = "") -> dict:
    mail = TempikClient()
    local = random_local()
    email = mail.create_inbox(local_part=local)
    if not email:
        raise AlpmeError("tempik returned no address")

    log(f"[{idx}] {email}")
    cli = AlpmeClient(proxy=proxy or None)
    cli.signup(email, password=rand_password(), name=rand_name(), ref=ref, promo=promo)

    plan = (cli.plan or {})
    log(f"  signup ok  plan={plan.get('name') or 'starter'} "
        f"{('(' + plan.get('message', '') + ')') if plan.get('message') else ''}")

    cli.login(email, cli.password)
    key = cli.create_key(f"alp-{idx}")
    quota = cli.quota()
    plan_slug = (quota.get("plan") or {}).get("slug", "?")
    log(f"  KEY {key[:18]}…  plan={plan_slug}")

    append(ACCOUNTS, f"{email}:{cli.password}")
    append(KEYS, key)
    return {"email": email, "password": cli.password, "key": key, "plan": plan_slug}


def main() -> int:
    ap = argparse.ArgumentParser(description="Alpme bulk registrar")
    ap.add_argument("-n", "--count", type=int, default=10)
    ap.add_argument("--gap", type=float, default=3.0, help="seconds between accounts")
    ap.add_argument("--promo", default=DEFAULT_PROMO, help="promo code ('' to skip)")
    ap.add_argument("--ref", default=DEFAULT_REF, help="referral code ('' to skip)")
    ap.add_argument("--retry", type=int, default=2, help="retries on transient errors")
    ap.add_argument("--no-9router", action="store_true", help="skip 9router injection")
    ap.add_argument("--no-rotate", dest="rotate", action="store_false",
                    help="do not rotate exit IP per account")
    ap.set_defaults(rotate=True)
    args = ap.parse_args()

    log(f"START n={args.count} promo={args.promo or '-'} ref={args.ref or '-'} "
        f"gap={args.gap}s 9router={'no' if args.no_9router else 'yes'}")

    ok = fail = 0
    for i in range(1, args.count + 1):
        attempt = 0
        while True:
            attempt += 1
            try:
                ip = rotate_ip() if args.rotate else "direct"
                log(f"  ip={ip}")
                res = register_one(args.promo, args.ref, i,
                                   proxy=BRIDGE if args.rotate else "")
                if not args.no_9router:
                    injected = inject_key(res["email"], res["key"])
                    log(f"  9router={'yes' if injected else 'NO'}")
                ok += 1
                break
            except AlpmeError as e:
                transient = any(t.lower() in str(e).lower() for t in TRANSIENT)
                if transient and attempt <= args.retry:
                    log(f"  retry {attempt}/{args.retry}: {str(e)[:70]}")
                    time.sleep(3)
                    continue
                log(f"  FAIL: {str(e)[:160]}")
                fail += 1
                break
            except Exception as e:
                if attempt <= args.retry:
                    log(f"  retry {attempt}/{args.retry}: {type(e).__name__}: {str(e)[:70]}")
                    time.sleep(3)
                    continue
                log(f"  FAIL: {type(e).__name__}: {str(e)[:160]}")
                fail += 1
                break
        if i < args.count:
            time.sleep(args.gap + random.uniform(0, 0.8))

    log(f"DONE  ok={ok}  fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
