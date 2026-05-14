# ============================================================================
# FILE: sasclouds/auth.py – Token scraping, auto-login, Playwright helpers
# ============================================================================
"""
Authentication utilities for SASClouds API.

Extracted from the monolithic sasclouds_api_scraper.py (1438 lines).
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import requests

from sasclouds.constants import _APP_DIR, _CONFIG_PATH

logger = logging.getLogger(__name__)


def fetch_token_from_page(
    username: str,
    password: str,
    login_url: str = "https://www.sasclouds.com/user/login",
    token_url: str = "https://www.sasclouds.com/user/login?action=token",
) -> Optional[str]:
    """
    Attempt to fetch an API token by logging in via the SASClouds website.

    This is a fallback method that tries to scrape the token from the login
    page.  It may not work if the website uses JavaScript-based authentication.

    Parameters
    ----------
    username : str
        SASClouds username.
    password : str
        SASClouds password.
    login_url : str
        URL for the login page.
    token_url : str
        URL to retrieve the token after login.

    Returns
    -------
    str or None
        The API token if successful, None otherwise.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })

    try:
        # Step 1: Get login page to capture any CSRF token
        login_resp = session.get(login_url, timeout=30)
        login_resp.raise_for_status()

        # Step 2: Submit login form
        login_data = {
            "username": username,
            "password": password,
        }
        # Try to extract CSRF token if present
        csrf_match = re.search(
            r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']',
            login_resp.text,
        )
        if csrf_match:
            login_data["csrf_token"] = csrf_match.group(1)

        post_resp = session.post(
            login_url,
            data=login_data,
            allow_redirects=True,
            timeout=30,
        )
        post_resp.raise_for_status()

        # Step 3: Try to get token
        token_resp = session.get(token_url, timeout=30)
        if token_resp.status_code == 200:
            data = token_resp.json()
            token = data.get("token") or data.get("access_token") or data.get("data", {}).get("token")
            if token:
                logger.info("Successfully fetched API token via login page.")
                return token

        logger.warning("Token not found in response from %s", token_url)
        return None

    except requests.RequestException as e:
        logger.error("Failed to fetch token from login page: %s", e)
        return None


def auto_login_and_capture_token(
    username: str,
    password: str,
    login_url: str = "https://www.sasclouds.com/user/login",
) -> Optional[str]:
    """
    Automate browser login using Playwright to capture the API token.

    This is the preferred method for obtaining a token as it handles
    JavaScript-based authentication flows.

    Parameters
    ----------
    username : str
        SASClouds username.
    password : str
        SASClouds password.
    login_url : str
        URL for the login page.

    Returns
    -------
    str or None
        The API token if captured successfully, None otherwise.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error(
            "Playwright is required for auto-login. "
            "Install with: pip install playwright && playwright install chromium"
        )
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            # Intercept network requests to capture the token
            captured_token = []

            def handle_response(response):
                if "token" in response.url.lower():
                    try:
                        data = response.json()
                        token = (
                            data.get("token")
                            or data.get("access_token")
                            or data.get("data", {}).get("token")
                        )
                        if token:
                            captured_token.append(token)
                    except Exception:
                        pass

            page.on("response", handle_response)

            # Navigate to login page
            page.goto(login_url, wait_until="networkidle", timeout=60000)

            # Fill login form
            page.fill('input[name="username"], input[type="text"]', username)
            page.fill('input[name="password"], input[type="password"]', password)

            # Submit
            page.click('button[type="submit"], input[type="submit"]')
            page.wait_for_timeout(5000)

            browser.close()

            if captured_token:
                logger.info("Successfully captured API token via Playwright.")
                return captured_token[0]

            logger.warning("No token captured during Playwright login.")
            return None

    except Exception as e:
        logger.error("Playwright auto-login failed: %s", e)
        return None


def scrape_token_via_browser(
    username: str,
    password: str,
    login_url: str = "https://www.sasclouds.com/user/login",
) -> Optional[str]:
    """
    Scrape the API token by opening a browser and logging in.

    This is a convenience wrapper around auto_login_and_capture_token.

    Parameters
    ----------
    username : str
        SASClouds username.
    password : str
        SASClouds password.
    login_url : str
        URL for the login page.

    Returns
    -------
    str or None
        The API token if captured successfully, None otherwise.
    """
    return auto_login_and_capture_token(username, password, login_url)


def ensure_playwright_browser() -> bool:
    """
    Ensure Playwright and its Chromium browser are installed.

    Returns
    -------
    bool
        True if Playwright is available, False otherwise.
    """
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                p.chromium.launch(headless=True).close()
            except Exception:
                logger.warning("Playwright Chromium browser not found. Run: playwright install chromium")
                return False
        return True
    except ImportError:
        logger.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return False
