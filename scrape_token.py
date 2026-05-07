"""
scrape_token.py  —  Capture the SASClouds auth token.

Usage:
    python scrape_token.py                  # headless, no login (page-load only)
    python scrape_token.py --visible        # visible browser, manual login
    python scrape_token.py --headless       # headless with credentials from env

Credentials (for automated login):
    Set environment variables before running:
        SASCLOUDS_USERNAME=your@email.com
        SASCLOUDS_PASSWORD=yourpassword
    Or add to .streamlit/secrets.toml:
        sasclouds_username = "your@email.com"
        sasclouds_password = "yourpassword"

First-time setup:
    pip install playwright
    playwright install chromium
"""

import argparse
import os
import sys
from sasclouds_api_scraper import auto_login_and_capture_token, scrape_token_via_browser

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture SASClouds auth token")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--visible", action="store_true",
                        help="Open a visible browser window")
    args = parser.parse_args()
    headless = not args.visible

    username = os.environ.get("SASCLOUDS_USERNAME", "")
    password = os.environ.get("SASCLOUDS_PASSWORD", "")

    if username and password:
        print(f"\nLogging in as {username} ({'headless' if headless else 'visible'})…")
        token = auto_login_and_capture_token(
            username, password,
            headless=headless,
            timeout_seconds=90,
        )
    else:
        if headless:
            print("\nNo credentials — trying page-load token capture (headless)…")
        else:
            print("\nNo credentials — opening visible browser. Log in manually and do a search.")
        token = scrape_token_via_browser(
            timeout_seconds=60 if headless else 300,
            headless=headless,
        )

    if token:
        print(f"[OK] Token saved to config.json  ({token[:12]}…{token[-6:]})")
        sys.exit(0)
    else:
        print("[FAILED] No token captured.")
        if headless and not username:
            print("  Try:  python scrape_token.py --visible")
        elif headless and username:
            print("  Login may have failed — check selectors.")
            print("  Try:  python scrape_token.py --visible  to watch the browser.")
        sys.exit(1)
