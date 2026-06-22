#!/usr/bin/env python3
"""Python translation of the original Tampermonkey logic for AM4.

This script mirrors the original behavior as closely as possible for Termux,
while keeping the implementation compatible with Python requests + Selenium.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import asyncio

# Optional pyppeteer fallback: when system Chromium isn't available (e.g. Termux),
# pyppeteer can download a headless Chromium via pip and be used as a replacement
# for limited browser interactions. Import lazily in setup_driver().

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def load_env_file(path: str = ENV_FILE) -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_env_file()

DEFAULT_BASE_URL = os.getenv("AM4_BASE_URL", "https://www.airlinemanager.com")
DEFAULT_FUEL_THRESHOLD = int(os.getenv("AM4_FUEL_THRESHOLD", "550"))
DEFAULT_CO2_THRESHOLD = int(os.getenv("AM4_CO2_THRESHOLD", "125"))
DEFAULT_EMAIL = os.getenv("AM4_EMAIL", "")
DEFAULT_PASSWORD = os.getenv("AM4_PASSWORD", "")
DEFAULT_CHROMIUM_PATH = os.getenv("AM4_CHROMIUM_PATH")
DEFAULT_CHROMEDRIVER_PATH = os.getenv("AM4_CHROMEDRIVER_PATH")
DEFAULT_DEPART_CHECK_INTERVAL_MINUTES = float(
    os.getenv("AM4_DEPART_CHECK_INTERVAL_MINUTES", "5")
)
DEFAULT_FUEL_CHECK_INTERVAL_MINUTES = float(
    os.getenv("AM4_FUEL_CHECK_INTERVAL_MINUTES", "1")
)
DEFAULT_DEPART_CHECK_INTERVAL_MIN_SECONDS = os.getenv(
    "AM4_DEPART_CHECK_INTERVAL_MIN_SECONDS"
)
DEFAULT_DEPART_CHECK_INTERVAL_MAX_SECONDS = os.getenv(
    "AM4_DEPART_CHECK_INTERVAL_MAX_SECONDS"
)
DEFAULT_FUEL_CHECK_INTERVAL_MIN_SECONDS = os.getenv(
    "AM4_FUEL_CHECK_INTERVAL_MIN_SECONDS"
)
DEFAULT_FUEL_CHECK_INTERVAL_MAX_SECONDS = os.getenv(
    "AM4_FUEL_CHECK_INTERVAL_MAX_SECONDS"
)
DEFAULT_DEPART_CHECK_INTERVAL_RANGE_SECONDS = os.getenv(
    "AM4_DEPART_CHECK_INTERVAL_RANGE_SECONDS"
)
DEFAULT_FUEL_CHECK_INTERVAL_RANGE_SECONDS = os.getenv(
    "AM4_FUEL_CHECK_INTERVAL_RANGE_SECONDS"
)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}")


class AM4Bot:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        fuel_threshold: int = DEFAULT_FUEL_THRESHOLD,
        co2_threshold: int = DEFAULT_CO2_THRESHOLD,
        email: str = DEFAULT_EMAIL,
        password: str = DEFAULT_PASSWORD,
        headless: bool = False,
        chromium_path: Optional[str] = DEFAULT_CHROMIUM_PATH,
        chromedriver_path: Optional[str] = DEFAULT_CHROMEDRIVER_PATH,
        depart_check_interval_minutes: float = DEFAULT_DEPART_CHECK_INTERVAL_MINUTES,
        fuel_check_interval_minutes: float = DEFAULT_FUEL_CHECK_INTERVAL_MINUTES,
        depart_check_interval_range_seconds: Optional[str] = DEFAULT_DEPART_CHECK_INTERVAL_RANGE_SECONDS,
        fuel_check_interval_range_seconds: Optional[str] = DEFAULT_FUEL_CHECK_INTERVAL_RANGE_SECONDS,
        depart_check_interval_min_seconds: Optional[int] = None,
        depart_check_interval_max_seconds: Optional[int] = None,
        fuel_check_interval_min_seconds: Optional[int] = None,
        fuel_check_interval_max_seconds: Optional[int] = None,
        mode: str = "auto",
    ):
        self.base_url = base_url.rstrip("/")
        self.fuel_threshold = fuel_threshold
        self.co2_threshold = co2_threshold
        self.email = email.strip()
        self.password = password
        self.headless = headless
        self.chromium_path = chromium_path
        self.chromedriver_path = chromedriver_path
        self.depart_check_interval_seconds = max(
            30, int(depart_check_interval_minutes * 60)
        )
        self.fuel_check_interval_seconds = max(
            30, int(fuel_check_interval_minutes * 60)
        )

        depart_min = (
            depart_check_interval_min_seconds
            if depart_check_interval_min_seconds is not None
            else self._parse_env_number(
                DEFAULT_DEPART_CHECK_INTERVAL_MIN_SECONDS
            )
        )
        depart_max = (
            depart_check_interval_max_seconds
            if depart_check_interval_max_seconds is not None
            else self._parse_env_number(
                DEFAULT_DEPART_CHECK_INTERVAL_MAX_SECONDS
            )
        )
        fuel_min = (
            fuel_check_interval_min_seconds
            if fuel_check_interval_min_seconds is not None
            else self._parse_env_number(
                DEFAULT_FUEL_CHECK_INTERVAL_MIN_SECONDS
            )
        )
        fuel_max = (
            fuel_check_interval_max_seconds
            if fuel_check_interval_max_seconds is not None
            else self._parse_env_number(
                DEFAULT_FUEL_CHECK_INTERVAL_MAX_SECONDS
            )
        )

        self.depart_check_interval_range_seconds = self._resolve_range(
            depart_check_interval_range_seconds,
            depart_min,
            depart_max,
        )
        self.fuel_check_interval_range_seconds = self._resolve_range(
            fuel_check_interval_range_seconds,
            fuel_min,
            fuel_max,
        )
        # Automation mode: 'auto' (try selenium, then pyppeteer), 'selenium',
        # 'pyppeteer', or 'http' (requests-only)
        self.mode = mode or "auto"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0 Mobile Safari/537.36"
                )
            }
        )
        self.driver: Optional[webdriver.Chrome] = None
        # pyppeteer runtime objects (created lazily)
        self.pyppeteer_browser = None
        self.pyppeteer_page = None
        self.pyppeteer_loop = None
        # Playwright runtime (sync API)
        self.playwright = None
        self.playwright_browser = None
        self.playwright_context = None
        self.playwright_page = None

    @staticmethod
    def _parse_env_number(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def parse_interval_range(value: Optional[str]) -> Optional[Tuple[int, int]]:
        if not value:
            return None

        parts = [part.strip() for part in re.split(r"[\s,;:-]+", value) if part.strip()]
        if len(parts) != 2:
            return None

        try:
            low, high = sorted(int(part) for part in parts)
        except ValueError:
            return None

        if low <= 0 or high <= 0:
            return None

        return (low, high)

    @classmethod
    def _resolve_range(
        cls,
        raw_value: Optional[str],
        min_value: Optional[int],
        max_value: Optional[int],
    ) -> Optional[Tuple[int, int]]:
        if raw_value:
            parsed = cls.parse_interval_range(raw_value)
            if parsed is not None:
                return parsed

        if min_value is not None and max_value is not None:
            return (min_value, max_value)

        return None

    def get_random_interval_seconds(
        self, min_seconds: int, max_seconds: int
    ) -> int:
        if min_seconds == max_seconds:
            return min_seconds
        return random.randint(min_seconds, max_seconds)

    def next_depart_check_delay(self) -> int:
        if self.depart_check_interval_range_seconds is not None:
            low, high = self.depart_check_interval_range_seconds
            return self.get_random_interval_seconds(low, high)
        return self.depart_check_interval_seconds

    def next_fuel_check_delay(self) -> int:
        if self.fuel_check_interval_range_seconds is not None:
            low, high = self.fuel_check_interval_range_seconds
            return self.get_random_interval_seconds(low, high)
        return self.fuel_check_interval_seconds

    def setup_driver(self) -> None:
        if self.driver is not None:
            return

        if self.mode == "http":
            log("Mode is http: skipping browser initialization.")
            return
        # If mode forces playwright, try that first
        if self.mode == "playwright":
            try:
                from playwright.sync_api import sync_playwright  # type: ignore

                log("Attempting to launch Playwright Chromium (headless).")
                p = sync_playwright().start()
                browser = p.chromium.launch(headless=self.headless, args=["--no-sandbox","--disable-dev-shm-usage","--window-size=430,900"]) 
                ua = self.session.headers.get("User-Agent")
                context = browser.new_context(user_agent=ua)
                page = context.new_page()
                self.playwright = p
                self.playwright_browser = browser
                self.playwright_context = context
                self.playwright_page = page
                log("Playwright Chromium launched and ready.")
                return
            except Exception as pw_exc:
                log(f"Playwright launch failed: {pw_exc}")
            # If Playwright failed in forced mode, stop here.
            if self.mode == "playwright":
                return

        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=430,900")
            chrome_options.add_argument("--user-agent=Mozilla/5.0")
            if self.chromium_path:
                chrome_options.binary_location = self.chromium_path
                log(f"Using Chromium binary: {self.chromium_path}")
            if self.chromedriver_path:
                service = Service(executable_path=self.chromedriver_path)
                self.driver = webdriver.Chrome(
                    service=service, options=chrome_options
                )
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            log("Browser driver initialized successfully.")
        except Exception as exc:
            log(
                f"Browser driver could not be started: {exc}. "
                "Some Selenium-based actions will be skipped."
            )
            self.driver = None
            # Attempt pyppeteer fallback when Selenium/Chromium can't start,
            # unless mode forces selenium only or http-only.
            if self.mode == "selenium":
                log("Mode is selenium and driver failed; not attempting pyppeteer fallback.")
                self.pyppeteer_browser = None
                self.pyppeteer_page = None
                self.pyppeteer_loop = None
                return
            if self.mode == "http":
                self.pyppeteer_browser = None
                self.pyppeteer_page = None
                self.pyppeteer_loop = None
                return

            # Attempt Playwright next (unless mode restricts), then pyppeteer fallback.
            try:
                from playwright.sync_api import sync_playwright  # type: ignore

                log("Attempting to launch Playwright Chromium (headless) as fallback.")
                p = sync_playwright().start()
                browser = p.chromium.launch(headless=self.headless, args=["--no-sandbox","--disable-dev-shm-usage","--window-size=430,900"]) 
                ua = self.session.headers.get("User-Agent")
                context = browser.new_context(user_agent=ua)
                page = context.new_page()
                self.playwright = p
                self.playwright_browser = browser
                self.playwright_context = context
                self.playwright_page = page
                log("Playwright Chromium launched and ready (fallback).")
            except Exception:
                # Attempt pyppeteer fallback when Selenium/Chromium and Playwright can't start.
                try:
                    from pyppeteer import launch  # type: ignore

                    log("Attempting to launch pyppeteer-managed Chromium (headless).")

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    browser = loop.run_until_complete(
                        launch(
                            headless=self.headless,
                            args=[
                                "--no-sandbox",
                                "--disable-dev-shm-usage",
                                "--window-size=430,900",
                            ],
                        )
                    )
                    page = loop.run_until_complete(browser.newPage())
                    ua = (
                        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0 Mobile Safari/537.36"
                    )
                    loop.run_until_complete(page.setUserAgent(ua))
                    self.pyppeteer_browser = browser
                    self.pyppeteer_page = page
                    self.pyppeteer_loop = loop
                    log("Pyppeteer Chromium launched and ready.")
                except Exception as pb_exc:
                    log(f"Pyppeteer fallback failed: {pb_exc}. No browser automation available.")
                    self.pyppeteer_browser = None
                    self.pyppeteer_page = None
                    self.pyppeteer_loop = None

    def close_driver(self) -> None:
        if self.driver is not None:
            self.driver.quit()
            self.driver = None
        if self.pyppeteer_browser is not None and self.pyppeteer_loop is not None:
            try:
                self.pyppeteer_loop.run_until_complete(self.pyppeteer_browser.close())
            except Exception:
                pass
            try:
                self.pyppeteer_loop.close()
            except Exception:
                pass
            self.pyppeteer_browser = None
            self.pyppeteer_page = None
            self.pyppeteer_loop = None
        if self.playwright_browser is not None and self.playwright is not None:
            try:
                if self.playwright_context is not None:
                    try:
                        self.playwright_context.close()
                    except Exception:
                        pass
                self.playwright_browser.close()
            except Exception:
                pass
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright_browser = None
            self.playwright_context = None
            self.playwright_page = None
            self.playwright = None

    def fetch(self, url: str) -> str:
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    def get_soup(self, url: str = "") -> BeautifulSoup:
        response = self.session.get(
            f"{self.base_url}/{url.lstrip('/')}" if url else self.base_url,
            timeout=30,
        )
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def sync_session_cookies(self) -> None:
        if self.driver is not None:
            for cookie in self.driver.get_cookies():
                self.session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain") or self.base_url.split("//", 1)[1],
                    path=cookie.get("path") or "/",
                )

        if self.playwright_context is not None:
            cookies = []
            base_domain = self.base_url.split("//", 1)[1].split("/", 1)[0]
            for cookie in self.session.cookies:
                domain = cookie.domain.lstrip(".") if cookie.domain else base_domain
                cookies.append(
                    {
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": domain,
                        "path": cookie.path or "/",
                    }
                )
            if cookies:
                try:
                    self.playwright_context.add_cookies(cookies)
                except Exception:
                    pass

        if self.pyppeteer_page is not None and self.pyppeteer_loop is not None:
            base_domain = self.base_url.split("//", 1)[1].split("/", 1)[0]
            for cookie in self.session.cookies:
                domain = cookie.domain.lstrip(".") if cookie.domain else base_domain
                cookie_dict = {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": domain,
                    "path": cookie.path or "/",
                }
                try:
                    self.pyppeteer_loop.run_until_complete(
                        self.pyppeteer_page.setCookie(cookie_dict)
                    )
                except Exception:
                    pass

    def ensure_logged_in(self) -> None:
        if not self.email or not self.password:
            log(
                "AM4_EMAIL and AM4_PASSWORD are not set; skipping automatic login. "
                "Set them to enable login automation."
            )
            return

        try:
            response = self.session.post(
                f"{self.base_url}/weblogin/login.php",
                data={
                    "lEmail": self.email,
                    "lPass": self.password,
                    "remember": "on",
                },
                timeout=30,
                allow_redirects=True,
            )
            log(
                f"Login endpoint response: {response.status_code} -> {response.url}"
            )

            page_response = self.session.get(self.base_url, timeout=30)
            page_text = page_response.text
            if "headerAccount" in page_text or 'id="headerAccount"' in page_text:
                log("Login automation completed successfully.")
                return

            if "loginForm" in page_text:
                log(
                    "Login attempt did not appear to succeed; the login form is still present."
                )
            else:
                log(
                    "Login response received, but the authenticated page markers were not found."
                )
        except requests.RequestException as exc:
            log(f"Login automation failed: {exc}")

    @staticmethod
    def parse_int(text: str) -> int:
        return int(re.sub(r"[^0-9-]", "", text))

    @staticmethod
    def is_success_response(response: requests.Response) -> bool:
        body = response.text.lower()
        failure_markers = [
            "error",
            "failed",
            "forbidden",
            "not found",
            "login form",
            "please login",
        ]
        return response.ok and not any(marker in body for marker in failure_markers)

    def get_bank_balance(self) -> Optional[int]:
        try:
            soup = self.get_soup()
            element = soup.select_one("#headerAccount")
            if not element:
                log("Could not find bank balance element.")
                return None
            balance = self.parse_int(element.get_text(" ", strip=True))
            log(f"Bank balance: {balance}")
            return balance
        except requests.RequestException as exc:
            log(f"Failed to fetch bank balance: {exc}")
            return None

    def get_fuel_snapshot(self) -> Optional[dict]:
        try:
            response = self.session.get(
                f"{self.base_url}/fuel.php", timeout=30
            )
            response.raise_for_status()
            html = response.text
            html_lower = html.lower()
            if "current price" not in html_lower and "fuelmain" not in html_lower:
                log("Fuel page did not expose the expected fuel panel.")
                return None

            price_match = re.search(
                r"Current price.*?\$\s*([0-9,]+)", html, re.S
            )
            rem_capacity_match = re.search(
                r"remCapacity[^>]*>([0-9,]+)</span>.*?/.*?([0-9,]+)\s*Lbs",
                html,
                re.S,
            )
            holding_match = re.search(
                r"id=['\"]holding['\"].*?>([0-9,]+)</span>", html, re.S
            )

            if not price_match or not rem_capacity_match:
                log("Could not parse fuel information from page content.")
                return None

            price = self.parse_int(price_match.group(1))
            remaining_capacity = self.parse_int(rem_capacity_match.group(1))
            total_capacity = self.parse_int(rem_capacity_match.group(2))
            holding = self.parse_int(holding_match.group(1)) if holding_match else 0

            log(
                "Fuel snapshot: "
                f"price={price}, capacity={remaining_capacity}/{total_capacity}, "
                f"holding={holding}"
            )
            return {
                "price": price,
                "remaining_capacity": remaining_capacity,
                "total_capacity": total_capacity,
                "holding": holding,
            }
        except requests.RequestException as exc:
            log(f"Failed to fetch fuel details: {exc}")
            return None

    def get_co2_snapshot(self) -> Optional[dict]:
        try:
            response = self.session.get(f"{self.base_url}/co2.php", timeout=30)
            response.raise_for_status()
            html = response.text
            # Try to find numeric price and capacity using regex
            price_match = re.search(r"Current price.*?\$\s*([0-9,]+)", html, re.S)
            rem_capacity_match = re.search(r"remCapacity[^>]*>([0-9,]+)</span>.*?/.*?([0-9,]+)", html, re.S)
            holding_match = re.search(r"id=['\"]holding['\"].*?>([0-9,]+)</span>", html, re.S)

            if not price_match:
                # Fallback: look for .price class in the HTML
                soup = BeautifulSoup(html, "html.parser")
                el = soup.select_one("#co2Main .price")
                price = self.parse_int(el.get_text(" ", strip=True)) if el else 0
            else:
                price = self.parse_int(price_match.group(1))

            if rem_capacity_match:
                remaining_capacity = self.parse_int(rem_capacity_match.group(1))
                total_capacity = self.parse_int(rem_capacity_match.group(2))
            else:
                remaining_capacity = 0
                total_capacity = 0

            holding = self.parse_int(holding_match.group(1)) if holding_match else 0

            log(
                "CO2 snapshot: "
                f"price={price}, capacity={remaining_capacity}/{total_capacity}, holding={holding}"
            )

            return {
                "price": price,
                "remaining_capacity": remaining_capacity,
                "total_capacity": total_capacity,
                "holding": holding,
            }
        except requests.RequestException as exc:
            log(f"Failed to fetch CO2 details: {exc}")
            return None

    def log_status_snapshot(self) -> None:
        balance = self.get_bank_balance()
        departure_count = "unknown"
        if self.driver is not None:
            try:
                departure_count = self.driver.find_element(
                    By.ID, "listDepartAmount"
                ).text.strip()
            except NoSuchElementException:
                departure_count = "not found"
            except Exception as exc:
                departure_count = f"error: {exc}"
        else:
            # If mode=http, attempt to get departure info via HTTP
            if self.mode == "http":
                try:
                    _, depart_text = self.get_departure_summary()
                    departure_count = depart_text
                except Exception as exc:
                    departure_count = f"error: {exc}"
            else:
                # Try pyppeteer fallback to obtain departure count
                if self.pyppeteer_page is not None:
                    try:
                        content = self.pyppeteer_loop.run_until_complete(
                            self.pyppeteer_page.evaluate(
                                "() => document.getElementById('listDepartAmount') ? document.getElementById('listDepartAmount').textContent.trim() : null"
                            )
                        )
                        departure_count = content if content else "not found"
                    except Exception as exc:
                        departure_count = f"error: {exc}"
                else:
                    departure_count = "browser unavailable"
        log(
            "Status snapshot: "
            f"balance={balance if balance is not None else 'n/a'}, "
            f"departures={departure_count}"
        )

    def check_fuel(self) -> None:
        snapshot = self.get_fuel_snapshot()
        if snapshot is None:
            return

        price = snapshot["price"]
        remaining_capacity = snapshot["remaining_capacity"]
        total_capacity = snapshot["total_capacity"]
        holding = snapshot["holding"]

        if total_capacity <= 0 or remaining_capacity >= total_capacity:
            log(
                "Fuel capacity is already full or unavailable; skipping purchase. "
                f"remaining={remaining_capacity}, total={total_capacity}, holding={holding}"
            )
            return

        if price > self.fuel_threshold:
            log(
                f"Fuel price {price} is above threshold {self.fuel_threshold}; skipping purchase."
            )
            return

        balance = self.get_bank_balance()
        if balance is None:
            return

        buyable = int(balance / price * 1000) if price else 0
        amount = min(buyable, remaining_capacity)
        if amount > 0:
            log(
                f"Attempting fuel purchase: {amount} liters at {price} each."
            )
            self.buy_fuel(amount, price)
        else:
            log("Not enough balance to buy fuel right now.")

    def get_departure_summary(self) -> tuple[int, str]:
        try:
            response = self.session.get(self.base_url, timeout=30)
            response.raise_for_status()
            html = response.text
            airc_total_match = re.search(
                r"var\s+aircTotal\s*=\s*([0-9]+)", html, re.S
            )
            list_depart_match = re.search(
                r"id=['\"]listDepartAmount['\"][^>]*>([^<]+)", html, re.S
            )
            airc_total = int(airc_total_match.group(1)) if airc_total_match else 0
            depart_text = (
                list_depart_match.group(1).strip()
                if list_depart_match
                else "unknown"
            )
            log(
                f"Departure summary: aircTotal={airc_total}, listDepartAmount={depart_text}"
            )
            return airc_total, depart_text
        except requests.RequestException as exc:
            log(f"Failed to fetch departure summary: {exc}")
            return 0, "unknown"

    def check_departures(self) -> None:
        if self.driver is not None:
            self.depart_all()
            return

        airc_total, depart_text = self.get_departure_summary()
        if airc_total <= 0 and depart_text in ("unknown", "all"):
            log(
                "No aircraft count is visible for departure; skipping HTTP departure attempt."
            )
            return

        endpoints = [
            ("x", f"{self.base_url}/route_depart.php?mode=all&ids=x"),
            ("all", f"{self.base_url}/route_depart.php?mode=all&ids=all"),
            ("default", f"{self.base_url}/route_depart.php?mode=all"),
        ]

        for label, url in endpoints:
            try:
                response = self.session.get(url, timeout=30)
                body = response.text
                snippet = body[:220].replace("\n", " ")
                if "No routes departed" in body or "All aircraft are inflight" in body:
                    log(
                        f"Departure endpoint {label} reported no eligible routes: "
                        f"{response.status_code} -> {snippet}"
                    )
                    continue
                if "playSound('depart')" in body or "toast(" in body:
                    log(
                        f"Departure endpoint {label} triggered a departure attempt: "
                        f"{response.status_code} -> {snippet}"
                    )
                    return
                log(
                    f"Departure endpoint {label} responded with: "
                    f"{response.status_code} -> {snippet}"
                )
            except requests.RequestException as exc:
                log(f"Departure endpoint {label} failed: {exc}")

        log(
            "No departure endpoint returned a confirmed route-depart signal for the current state."
        )

    def start_eco_campaign(self) -> None:
        url = f"{self.base_url}/marketing_new.php?type=5&mode=do&c=1"
        try:
            response = self.session.get(url, timeout=30)
            success = self.is_success_response(response)
            log(
                f"Eco campaign {'succeeded' if success else 'did not confirm success'}: "
                f"{response.status_code} -> {response.text[:140]}"
            )
        except requests.RequestException as exc:
            log(f"Eco-friendly campaign request failed: {exc}")

    def better_auto_price(self) -> None:
        # Try Selenium first; if unavailable use pyppeteer to extract the onclick
        self.setup_driver()
        if self.driver is not None:
            try:
                self.driver.get(self.base_url)
                wait = WebDriverWait(self.driver, 15)
                intro = wait.until(EC.presence_of_element_located((By.ID, "introAuto")))
                onclick = intro.get_attribute("onclick") or ""
                if not onclick:
                    log("No onclick attribute found for introAuto.")
                    return
                values_part = onclick[onclick.find("(") + 1 : onclick.find(")")]
                values = [item.strip() for item in values_part.split(",")]
                price_values = values[:4]
                log(
                    "Auto-price values detected: "
                    f"{price_values} (status: ready for review)."
                )
            except (TimeoutException, NoSuchElementException):
                log("Could not find auto-price button on the page.")
            except Exception as exc:
                log(f"Auto-price check failed: {exc}")
            return

        if self.pyppeteer_page is not None:
            try:
                loop = self.pyppeteer_loop
                loop.run_until_complete(self.pyppeteer_page.goto(self.base_url))
                onclick = loop.run_until_complete(
                    self.pyppeteer_page.evaluate(
                        "() => (document.getElementById('introAuto')||{}).getAttribute('onclick') || ''"
                    )
                )
                if not onclick:
                    log("No onclick attribute found for introAuto (pyppeteer).")
                    return
                values_part = onclick[onclick.find("(") + 1 : onclick.find(")")]
                values = [item.strip() for item in values_part.split(",")]
                price_values = values[:4]
                log(
                    "Auto-price values detected (pyppeteer): "
                    f"{price_values} (status: ready for review)."
                )
            except Exception as exc:
                log(f"Could not find auto-price button via pyppeteer: {exc}")

    def depart_all(self) -> None:
        # Try Selenium first, then pyppeteer fallback for clicking the departure UI
        if self.driver is not None:
            try:
                count = self.driver.find_element(By.ID, "listDepartAmount")
                flight_count = count.text.strip()
                log(
                    f"Departure panel shows {flight_count} flight(s) ready to depart. "
                    "Exact aircraft details will be logged once the flight list is available."
                )
                if flight_count != "0":
                    self.start_eco_campaign()
                    time.sleep(1)
                    button = count.find_element(By.XPATH, "..")
                    self.driver.execute_script("arguments[0].click();", button)
                    log(
                        f"✅ Departure action triggered for {flight_count} flight(s)."
                    )
                return
            except NoSuchElementException:
                log("Could not find departure elements (selenium).")

        if self.pyppeteer_page is not None and self.pyppeteer_loop is not None:
            try:
                loop = self.pyppeteer_loop
                # Ensure main page is loaded to read the element
                loop.run_until_complete(self.pyppeteer_page.goto(self.base_url))
                flight_count = loop.run_until_complete(
                    self.pyppeteer_page.evaluate(
                        "() => { const el = document.getElementById('listDepartAmount'); return el ? el.textContent.trim() : null }"
                    )
                )
                if flight_count is None:
                    log("Could not find departure elements (pyppeteer).")
                    return
                log(
                    f"Departure panel shows {flight_count} flight(s) ready to depart."
                )
                if flight_count != "0":
                    self.start_eco_campaign()
                    time.sleep(1)
                    # Click the parent element to trigger departure
                    loop.run_until_complete(
                        self.pyppeteer_page.evaluate(
                            "() => { const el = document.getElementById('listDepartAmount'); if (el && el.parentElement) el.parentElement.click(); }"
                        )
                    )
                    log(f"✅ Departure action triggered for {flight_count} flight(s) (pyppeteer).")
            except Exception as exc:
                log(f"Departure via pyppeteer failed: {exc}")
            return

        log("Browser automation is unavailable; cannot trigger departure UI clicks.")

    def auto_depart_routine(self) -> None:
        # Human-like random delay between roughly 4 and 7 minutes.
        min_wait = 240
        max_wait = 420
        wait_seconds = random.uniform(min_wait, max_wait)
        log(
            f"Next auto-depart check in {wait_seconds / 60:.1f} minutes "
            f"(randomized range: {min_wait // 60} to {max_wait // 60} min)."
        )
        time.sleep(wait_seconds)
        self.depart_all()

    def buy_fuel(self, amount: int, price: int = 0) -> None:
        url = f"{self.base_url}/fuel.php?mode=do&amount={amount}"
        try:
            response = self.session.get(url, timeout=30)
            status = "succeeded" if self.is_success_response(response) else "did not confirm success"
            log(
                f"✅ Buying fuel: {amount} liters at ~{price} each -> {status} "
                f"({response.status_code})."
            )
            if not self.is_success_response(response):
                log(f"Fuel purchase response snippet: {response.text[:180]}")
        except requests.RequestException as exc:
            log(f"Fuel buy failed: {exc}")

    def buy_co2(self, amount: int, price: int = 0) -> None:
        url = f"{self.base_url}/co2.php?mode=do&amount={amount}"
        try:
            response = self.session.get(url, timeout=30)
            status = "succeeded" if self.is_success_response(response) else "did not confirm success"
            log(
                f"✅ Buying CO2: {amount} units at ~{price} each -> {status} "
                f"({response.status_code})."
            )
            if not self.is_success_response(response):
                log(f"CO2 purchase response snippet: {response.text[:180]}")
        except requests.RequestException as exc:
            log(f"CO2 buy failed: {exc}")

    def scan_consumables(self) -> None:
        # Prefer Selenium when available. If mode is http, always use HTTP
        # requests to read fuel/co2 pages. Otherwise, fallback to pyppeteer
        # when Selenium is unavailable.
        if self.driver is not None:
            try:
                self.driver.execute_script(
                    "popup('fuel.php', 'Fuel', false, false, true);"
                )
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "fuelMain"))
                )
                fuel_panel = self.driver.find_element(By.ID, "fuelMain")
                fuel_price = fuel_panel.find_element(By.CSS_SELECTOR, ".price")
                fuel_price_value = self.parse_int(fuel_price.text)
                log(
                    "Fuel snapshot: "
                    f"current price={fuel_price_value}, "
                    f"threshold={self.fuel_threshold}"
                )

                if fuel_price_value <= self.fuel_threshold:
                    capacity = self.parse_int(
                        fuel_panel.find_element(By.CSS_SELECTOR, ".capacity").text
                    )
                    balance = self.get_bank_balance()
                    if balance is None:
                        return
                    buyable = int(balance / fuel_price_value * 1000) if fuel_price_value else 0
                    amount = min(buyable, capacity)
                    if amount > 0:
                        log(
                            f"Attempting fuel purchase: {amount} liters at {fuel_price_value} each."
                        )
                        self.buy_fuel(amount, fuel_price_value)
                    else:
                        log("Not enough balance to buy fuel right now.")

                # CO2 panel is opened by clicking the button in the popup.
                try:
                    self.driver.find_element(By.ID, "popBtn2").click()
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.ID, "co2Main"))
                    )
                    co2_panel = self.driver.find_element(By.ID, "co2Main")
                    co2_price = co2_panel.find_element(By.CSS_SELECTOR, ".price")
                    co2_price_value = self.parse_int(co2_price.text)
                    log(
                        "CO2 snapshot: "
                        f"current price={co2_price_value}, "
                        f"threshold={self.co2_threshold}"
                    )
                    if co2_price_value <= self.co2_threshold:
                        capacity = self.parse_int(
                            co2_panel.find_element(By.CSS_SELECTOR, ".capacity").text
                        )
                        balance = self.get_bank_balance()
                        if balance is None:
                            return
                        buyable = int(balance / co2_price_value * 1000) if co2_price_value else 0
                        amount = min(buyable, capacity)
                        if amount > 0:
                            log(
                                f"Attempting CO2 purchase: {amount} units at {co2_price_value} each."
                            )
                            self.buy_co2(amount, co2_price_value)
                        else:
                            log("Not enough balance to buy CO2 right now.")
                except NoSuchElementException:
                    log("CO2 popup button was not found.")
            except TimeoutException:
                log("Timed out while waiting for the consumable windows.")
            return

        # If explicit http mode, use requests-only parsing regardless of
        # available browser automation. Use get_fuel_snapshot() which has
        # more robust parsing, and implement get_co2_snapshot() for CO2.
        if self.mode == "http":
            try:
                fuel_snapshot = self.get_fuel_snapshot()
                if not fuel_snapshot:
                    log("Fuel snapshot not available (http mode).")
                else:
                    fuel_price_value = fuel_snapshot.get("price", 0)
                    capacity = fuel_snapshot.get("remaining_capacity", 0)
                    log(f"Fuel snapshot (http): current price={fuel_price_value}, threshold={self.fuel_threshold}")
                    if fuel_price_value <= self.fuel_threshold and capacity > 0:
                        balance = self.get_bank_balance()
                        if balance is None:
                            return
                        buyable = int(balance / fuel_price_value * 1000) if fuel_price_value else 0
                        amount = min(buyable, capacity)
                        if amount > 0:
                            log(f"Attempting fuel purchase: {amount} liters at {fuel_price_value} each.")
                            self.buy_fuel(amount, fuel_price_value)
                        else:
                            log("Not enough balance to buy fuel right now.")

                # CO2 via a lightweight snapshot
                co2_snapshot = self.get_co2_snapshot()
                if not co2_snapshot:
                    log("CO2 snapshot not available (http mode).")
                else:
                    co2_price_value = co2_snapshot.get("price", 0)
                    capacity = co2_snapshot.get("remaining_capacity", 0)
                    log(f"CO2 snapshot (http): current price={co2_price_value}, threshold={self.co2_threshold}")
                    if co2_price_value <= self.co2_threshold and capacity > 0:
                        balance = self.get_bank_balance()
                        if balance is None:
                            return
                        buyable = int(balance / co2_price_value * 1000) if co2_price_value else 0
                        amount = min(buyable, capacity)
                        if amount > 0:
                            log(f"Attempting CO2 purchase: {amount} units at {co2_price_value} each.")
                            self.buy_co2(amount, co2_price_value)
                        else:
                            log("Not enough balance to buy CO2 right now.")
            except requests.RequestException as exc:
                log(f"Consumables scan via HTTP failed: {exc}")
            return

        # Playwright fallback: open fuel.php directly and parse DOM
        if self.playwright_page is not None and self.playwright is not None:
            try:
                page = self.playwright_page
                page.goto(f"{self.base_url}/fuel.php")
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                fuel_panel = soup.select_one("#fuelMain")
                if not fuel_panel:
                    log("Fuel panel not present on fuel.php (playwright).")
                else:
                    price_el = fuel_panel.select_one(".price")
                    fuel_price_value = self.parse_int(price_el.get_text(" ", strip=True)) if price_el else 0
                    log(
                        "Fuel snapshot (playwright): "
                        f"current price={fuel_price_value}, threshold={self.fuel_threshold}"
                    )

                    if fuel_price_value <= self.fuel_threshold:
                        capacity_el = fuel_panel.select_one(".capacity")
                        capacity = self.parse_int(capacity_el.get_text(" ", strip=True)) if capacity_el else 0
                        balance = self.get_bank_balance()
                        if balance is None:
                            return
                        buyable = int(balance / fuel_price_value * 1000) if fuel_price_value else 0
                        amount = min(buyable, capacity)
                        if amount > 0:
                            log(f"Attempting fuel purchase: {amount} liters at {fuel_price_value} each.")
                            self.buy_fuel(amount, fuel_price_value)
                        else:
                            log("Not enough balance to buy fuel right now.")

                # Try CO2 page as well
                page.goto(f"{self.base_url}/co2.php")
                html2 = page.content()
                soup2 = BeautifulSoup(html2, "html.parser")
                co2_panel = soup2.select_one("#co2Main")
                if co2_panel:
                    price_el = co2_panel.select_one(".price")
                    co2_price_value = self.parse_int(price_el.get_text(" ", strip=True)) if price_el else 0
                    log(
                        "CO2 snapshot (playwright): "
                        f"current price={co2_price_value}, threshold={self.co2_threshold}"
                    )
                    if co2_price_value <= self.co2_threshold:
                        capacity_el = co2_panel.select_one(".capacity")
                        capacity = self.parse_int(capacity_el.get_text(" ", strip=True)) if capacity_el else 0
                        balance = self.get_bank_balance()
                        if balance is None:
                            return
                        buyable = int(balance / co2_price_value * 1000) if co2_price_value else 0
                        amount = min(buyable, capacity)
                        if amount > 0:
                            log(f"Attempting CO2 purchase: {amount} units at {co2_price_value} each.")
                            self.buy_co2(amount, co2_price_value)
                        else:
                            log("Not enough balance to buy CO2 right now.")
                else:
                    log("CO2 panel not present on co2.php (playwright).")
            except Exception as exc:
                log(f"Consumables scan via playwright failed: {exc}")
            return

        # pyppeteer fallback: open fuel.php directly and parse DOM
        if self.pyppeteer_page is not None and self.pyppeteer_loop is not None:
            try:
                loop = self.pyppeteer_loop
                loop.run_until_complete(self.pyppeteer_page.goto(f"{self.base_url}/fuel.php"))
                html = loop.run_until_complete(self.pyppeteer_page.content())
                soup = BeautifulSoup(html, "html.parser")
                fuel_panel = soup.select_one("#fuelMain")
                if not fuel_panel:
                    log("Fuel panel not present on fuel.php (pyppeteer).")
                    return
                price_el = fuel_panel.select_one(".price")
                fuel_price_value = self.parse_int(price_el.get_text(" ", strip=True)) if price_el else 0
                log(
                    "Fuel snapshot (pyppeteer): "
                    f"current price={fuel_price_value}, threshold={self.fuel_threshold}"
                )

                if fuel_price_value <= self.fuel_threshold:
                    capacity_el = fuel_panel.select_one(".capacity")
                    capacity = self.parse_int(capacity_el.get_text(" ", strip=True)) if capacity_el else 0
                    balance = self.get_bank_balance()
                    if balance is None:
                        return
                    buyable = int(balance / fuel_price_value * 1000) if fuel_price_value else 0
                    amount = min(buyable, capacity)
                    if amount > 0:
                        log(f"Attempting fuel purchase: {amount} liters at {fuel_price_value} each.")
                        self.buy_fuel(amount, fuel_price_value)
                    else:
                        log("Not enough balance to buy fuel right now.")
            except Exception as exc:
                log(f"Consumables scan via pyppeteer failed: {exc}")
            return
        log("Browser automation is unavailable; cannot inspect consumable windows.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Python translation of the AM4 bot logic.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL for the game site.",
    )
    parser.add_argument(
        "--fuel-threshold",
        type=int,
        default=DEFAULT_FUEL_THRESHOLD,
        help="Fuel price threshold.",
    )
    parser.add_argument(
        "--co2-threshold",
        type=int,
        default=DEFAULT_CO2_THRESHOLD,
        help="CO2 price threshold.",
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help="Email used for the website login form.",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="Password used for the website login form.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode when available.",
    )
    parser.add_argument(
        "--chromium-path",
        default=DEFAULT_CHROMIUM_PATH,
        help="Path to the Chromium/Chrome binary to use for Selenium.",
    )
    parser.add_argument(
        "--chromedriver-path",
        default=DEFAULT_CHROMEDRIVER_PATH,
        help="Path to the ChromeDriver executable to use for Selenium.",
    )
    parser.add_argument(
        "--depart-check-interval-minutes",
        type=float,
        default=DEFAULT_DEPART_CHECK_INTERVAL_MINUTES,
        help="How often to check for flights to depart (in minutes).",
    )
    parser.add_argument(
        "--fuel-check-interval-minutes",
        type=float,
        default=DEFAULT_FUEL_CHECK_INTERVAL_MINUTES,
        help="How often to check fuel price and buy if needed (in minutes).",
    )
    parser.add_argument(
        "--depart-check-interval-range-seconds",
        default=DEFAULT_DEPART_CHECK_INTERVAL_RANGE_SECONDS,
        help=(
            "Optional random range for departure checks, in seconds. "
            "Example: 1000-5000 or 1000,5000"
        ),
    )
    parser.add_argument(
        "--fuel-check-interval-range-seconds",
        default=DEFAULT_FUEL_CHECK_INTERVAL_RANGE_SECONDS,
        help=(
            "Optional random range for fuel checks, in seconds. "
            "Example: 600-1800 or 600,1800"
        ),
    )
    parser.add_argument(
        "--depart-check-interval-min-seconds",
        type=int,
        default=None,
        help="Optional lower bound for depart random interval range (seconds).",
    )
    parser.add_argument(
        "--depart-check-interval-max-seconds",
        type=int,
        default=None,
        help="Optional upper bound for depart random interval range (seconds).",
    )
    parser.add_argument(
        "--fuel-check-interval-min-seconds",
        type=int,
        default=None,
        help="Optional lower bound for fuel random interval range (seconds).",
    )
    parser.add_argument(
        "--fuel-check-interval-max-seconds",
        type=int,
        default=None,
        help="Optional upper bound for fuel random interval range (seconds).",
    )
    parser.add_argument(
        "--configure-intervals",
        "--change-intervals",
        "--change-interval",
        dest="configure_intervals",
        action="store_true",
        help="Interactively save interval range settings to .env once.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one cycle and exit instead of looping.",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "selenium", "pyppeteer", "playwright", "http"),
        default="auto",
        help="Automation mode: auto/selenium/pyppeteer/playwright/http (http forces requests-only).",
    )
    return parser.parse_args()


def write_interval_settings_to_env(
    depart_min: int,
    depart_max: int,
    fuel_min: int,
    fuel_max: int,
) -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    pairs = {
        "AM4_DEPART_CHECK_INTERVAL_MIN_SECONDS": str(depart_min),
        "AM4_DEPART_CHECK_INTERVAL_MAX_SECONDS": str(depart_max),
        "AM4_FUEL_CHECK_INTERVAL_MIN_SECONDS": str(fuel_min),
        "AM4_FUEL_CHECK_INTERVAL_MAX_SECONDS": str(fuel_max),
    }

    existing_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as file:
            existing_lines = file.readlines()

    updated_lines = []
    existing_keys = set()
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            updated_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        existing_keys.add(key)
        if key in pairs:
            updated_lines.append(f"{key}={pairs[key]}\n")
        else:
            updated_lines.append(line)

    for key in pairs:
        if key not in existing_keys:
            updated_lines.append(f"{key}={pairs[key]}\n")

    with open(env_path, "w", encoding="utf-8") as file:
        file.writelines(updated_lines)

    log(f"Saved interval settings to {env_path}")


def prompt_for_interval_settings() -> None:
    print("Enter interval values in seconds.")
    depart_min = int(input("Depart interval min (seconds): ").strip())
    depart_max = int(input("Depart interval max (seconds): ").strip())
    fuel_min = int(input("Fuel interval min (seconds): ").strip())
    fuel_max = int(input("Fuel interval max (seconds): ").strip())

    if depart_min <= 0 or depart_max <= 0 or fuel_min <= 0 or fuel_max <= 0:
        raise ValueError("All values must be positive.")

    write_interval_settings_to_env(depart_min, depart_max, fuel_min, fuel_max)


def main() -> int:
    args = parse_args()

    if args.configure_intervals:
        try:
            prompt_for_interval_settings()
        except KeyboardInterrupt:
            log("Interval configuration cancelled.")
        except Exception as exc:
            log(f"Interval configuration failed: {exc}")
        return 0

    bot = AM4Bot(
        base_url=args.base_url,
        fuel_threshold=args.fuel_threshold,
        co2_threshold=args.co2_threshold,
        email=args.email,
        password=args.password,
        headless=args.headless,
        chromium_path=args.chromium_path,
        chromedriver_path=args.chromedriver_path,
        depart_check_interval_minutes=args.depart_check_interval_minutes,
        fuel_check_interval_minutes=args.fuel_check_interval_minutes,
        depart_check_interval_range_seconds=args.depart_check_interval_range_seconds,
        fuel_check_interval_range_seconds=args.fuel_check_interval_range_seconds,
        depart_check_interval_min_seconds=args.depart_check_interval_min_seconds,
        depart_check_interval_max_seconds=args.depart_check_interval_max_seconds,
        fuel_check_interval_min_seconds=args.fuel_check_interval_min_seconds,
        fuel_check_interval_max_seconds=args.fuel_check_interval_max_seconds,
        mode=args.mode,
    )

    try:
        bot.setup_driver()
        bot.ensure_logged_in()

        last_depart_check = time.monotonic()
        last_fuel_check = time.monotonic()
        depart_delay_seconds = bot.next_depart_check_delay()
        fuel_delay_seconds = bot.next_fuel_check_delay()

        while True:
            now = time.monotonic()
            bot.log_status_snapshot()

            if now - last_depart_check >= depart_delay_seconds:
                bot.check_departures()
                last_depart_check = now
                depart_delay_seconds = bot.next_depart_check_delay()
                log(
                    "Next departure check scheduled in "
                    f"{depart_delay_seconds} seconds."
                )

            if now - last_fuel_check >= fuel_delay_seconds:
                bot.check_fuel()
                last_fuel_check = now
                fuel_delay_seconds = bot.next_fuel_check_delay()
                log(
                    "Next fuel check scheduled in "
                    f"{fuel_delay_seconds} seconds."
                )

            if args.once:
                break

            time.sleep(5)
    except KeyboardInterrupt:
        log("Bot interrupted by user.")
    finally:
        bot.close_driver()

    return 0


if __name__ == "__main__":
    sys.exit(main())
