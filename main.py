#!/usr/bin/env python3
"""Alpme CLI — register, mint keys, check quota, test models."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpme_client import AlpmeClient, AlpmeError, rand_password, rand_name
from tempmail import TempikClient, random_local

ROOT = Path(__file__).resolve().parent
ACCOUNTS = ROOT / "accounts.txt"
KEYS = ROOT / "keys.txt"


def cmd_register(a):
    mail = TempikClient()
    email = mail.create_inbox(local_part=random_local())
    cli = AlpmeClient()
    cli.signup(email, password=rand_password(), name=rand_name(), ref=a.ref, promo=a.promo)
    cli.login(email, cli.password)
    key = cli.create_key("alp-cli")
    plan = (cli.quota().get("plan") or {})
    print(f"email : {email}")
    print(f"pass  : {cli.password}")
    print(f"key   : {key}")
    print(f"plan  : {plan.get('slug')}  ({plan.get('window_5h')}/5h, {plan.get('window_week')}/wk)")
    with ACCOUNTS.open("a") as f:
        f.write(f"{email}:{cli.password}\n")
    with KEYS.open("a") as f:
        f.write(key + "\n")


def cmd_login(a):
    cli = AlpmeClient()
    cli.login(a.email, a.password)
    if a.mint:
        key = cli.create_key("alp-cli")
        print(key)
    q = cli.quota()
    plan = q.get("plan") or {}
    print(f"plan   : {plan.get('slug')} {plan.get('name')}")
    print(f"limits : ${plan.get('window_5h')}/5h · ${plan.get('window_week')}/week")
    print(f"keys   : {q.get('active')}/{q.get('max')}")


def cmd_models(a):
    key = a.key or (KEYS.read_text().split()[0] if KEYS.exists() else "")
    if not key:
        raise SystemExit("no key: pass --key or run register first")
    ids = AlpmeClient.models(key)
    print(f"{len(ids)} models")
    for m in ids:
        print(" ", m)


def cmd_test(a):
    key = a.key or (KEYS.read_text().split()[0] if KEYS.exists() else "")
    if not key:
        raise SystemExit("no key")
    models = [a.model] if a.model else ["gpt-6-astra", "claude-opus-5-5",
                                        "gemini-4-argon", "grok-4.7"]
    for m in models:
        try:
            d = AlpmeClient.chat(key, m, [{"role": "user", "content": "What is 2+2? One word."}], 50)
            txt = (d["choices"][0]["message"].get("content") or "").strip()
            print(f"{m:22} 200 {txt[:30]!r}")
        except AlpmeError as e:
            print(f"{m:22} {e.status} {str(e)[:90]}")


def cmd_quota(a):
    cli = AlpmeClient()
    cli.login(a.email, a.password)
    print(json.dumps(cli.list_keys(), indent=1)[:1200])


def main() -> int:
    ap = argparse.ArgumentParser(prog="alpme")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("register", help="create one account + key")
    r.add_argument("--promo", default="ALP27")
    r.add_argument("--ref", default="ariqnetz7-3b6e")
    r.set_defaults(func=cmd_register)

    l = sub.add_parser("login", help="log in and show plan")
    l.add_argument("-e", "--email", required=True)
    l.add_argument("-p", "--password", required=True)
    l.add_argument("--mint", action="store_true", help="also mint a fresh key")
    l.set_defaults(func=cmd_login)

    m = sub.add_parser("models", help="list models")
    m.add_argument("--key")
    m.set_defaults(func=cmd_models)

    t = sub.add_parser("test", help="send a test prompt")
    t.add_argument("--key")
    t.add_argument("--model")
    t.set_defaults(func=cmd_test)

    q = sub.add_parser("quota", help="dump quota JSON")
    q.add_argument("-e", "--email", required=True)
    q.add_argument("-p", "--password", required=True)
    q.set_defaults(func=cmd_quota)

    a = ap.parse_args()
    try:
        a.func(a)
    except AlpmeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
