#!/usr/bin/env python3
"""IGG login automation for Doomsday: Last Survivors.

Usage:
  python3 login_tool.py <accounts_file> [--prefix PREFIX]

Prepares session data and loads it into a Wine prefix for each account.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

def main():
    parser = argparse.ArgumentParser(description="IGG login automation")
    parser.add_argument("accounts_file", help="email:password per line")
    parser.add_argument("--prefix", default="/home/swong/dls/wineprefix_proton",
                        help="Wine prefix to install sessions into")
    parser.add_argument("--output-dir", default="/tmp/igg_sessions")
    args = parser.parse_args()
    
    accounts = []
    with open(args.accounts_file) as f:
        for line in f:
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                accounts.append(tuple(line.split(':', 1)))
    
    print(f"Loaded {len(accounts)} accounts")
    os.makedirs(args.output_dir, exist_ok=True)
    
    for email, pw in accounts:
        print(f"\n=== {email} ===")
        out = os.path.join(args.output_dir, email.split('@')[0])
        login_account(email, pw, out)
        if os.path.exists(os.path.join(out, "igg_session.reg")):
            apply_session(out, args.prefix)
            print(f"  ✓ Ready to launch with {args.prefix}")

def login_account(email, password, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        page = ctx.new_page()
        try:
            page.goto("https://passport.igg.com/login", timeout=30000)
            page.wait_for_load_state("networkidle")
            page.fill("#email_login", email)
            page.fill("#email_password", password)
            page.click(".btn-email-login")
            page.wait_for_timeout(5000)
            
            sso = next((c["value"] for c in ctx.cookies() if c["name"] == "gpc_sso_token"), None)
            if not sso:
                print("  ✗ No SSO token in cookies")
                page.screenshot(path=os.path.join(output_dir, "fail.png"))
                return
            
            payload = json.loads(base64.urlsafe_b64decode(sso.split(".")[1] + "=="))
            gpcid = payload["sub"]
            now = int(time.time())
            exp = payload.get("exp", now + 604800)
            print(f"  ✓ GPCID={gpcid}, expires {datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()}")
            
            with open(os.path.join(output_dir, "sso_token.txt"), "w") as f:
                f.write(sso)
            
            # Generate .reg file
            reg = f"""Windows Registry Editor Version 5.00

[HKEY_CURRENT_USER\\Software\\IGG\\Doomsday: Last Survivors]
"gpc.sdk.account.gpcid.on.first.logined_h3709894508"=hex:{b2h(gpcid.encode() + b'\\x00')}
"gpc.sdk.account.gpcid_h3320339899"=hex:{b2h(gpcid.encode() + b'\\x00')}
"gpc.sdk.account.last.refresh.session.timestamp_h259696459"=hex:{b2h(str(now).encode() + b'\\x00')}
"gpc.sdk.account.login.type.on.first.logined_h2796125376"=hex:{b2h(b'guest\\x00')}
"gpc.sdk.account.login.type_h2855320023"=hex:{b2h(b'guest\\x00')}
"gpc.sdk.account.ssotoken.time.to.create_h4153080402"=hex:{b2h(str(now - 86400).encode() + b'\\x00')}
"gpc.sdk.account.ssotoken.time.to.verify_h3423459393"=hex:{b2h(str(now).encode() + b'\\x00')}
"_PRE_LOGIN_TYPE__h2738857529"=dword:00000001
"""
            with open(os.path.join(output_dir, "igg_session.reg"), "w") as f:
                f.write(reg)
            print(f"  ✓ Session reg written")
        except Exception as e:
            print(f"  ✗ {e}")
        finally:
            browser.close()

def apply_session(session_dir, prefix):
    reg = os.path.join(session_dir, "igg_session.reg")
    if not os.path.exists(reg):
        print(f"  No session reg at {reg}")
        return
    subprocess.run(["/opt/wine-proton/bin/wine", "reg", "import", reg],
                   env={"WINEPREFIX": prefix}, capture_output=True, timeout=30)

def b2h(data: bytes) -> str:
    return ",".join(f"{b:02x}" for b in data)

if __name__ == "__main__":
    main()
