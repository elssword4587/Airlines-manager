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
from typing import Optional

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

DEFAULT_BASE_URL = os.getenv("AM4_BASE_URL", "https://www.airlinemanager.com")
DEFAULT_FUEL_THRESHOLD = int(os.getenv("AM4_FUEL_THRESHOLD", "550"))
DEFAULT_CO2_THRESHOLD = int(os.getenv("AM4_CO2_THRESHOLD", "125"))
DEFAULT_EMAIL = os.getenv("AM4_EMAIL", "")
DEFAULT_PASSWORD = os.getenv("AM4_PASSWORD", "")


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
    ):
        self.base_url = base_url.rstrip("/")
        self.fuel_threshold = fuel_threshold
        self.co2_threshold = co2_threshold
        self.email = email.strip()
        self.password = password
        self.headless = headless
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

    def setup_driver(self) -> None:
        if self.driver is not None:
            return

        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=430,900")
            chrome_options.add_argument("--user-agent=Mozilla/5.0")
            self.driver = webdriver.Chrome(options=chrome_options)
            log("Browser driver initialized successfully.")
        except Exception as exc:
            log(
                f"Browser driver could not be started: {exc}. "
                "Some Selenium-based actions will be skipped."
            )
            self.driver = None

    def close_driver(self) -> None:
        if self.driver is not None:
            self.driver.quit()
            self.driver = None

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
        if self.driver is None:
            return
        for cookie in self.driver.get_cookies():
            self.session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain") or self.base_url.split("//", 1)[1],
                path=cookie.get("path") or "/",
            )

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
        self.setup_driver()
        if self.driver is None:
            log("Skipping auto-price check because browser automation is unavailable.")
            return

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

    def depart_all(self) -> None:
        if self.driver is None:
            log("Selenium driver is required to click the departure button.")
            return

        try:
            count = self.driver.find_element(By.ID, "listDepartAmount")
            flight_count = count.text.strip()
            log(f"{flight_count} flight(s) to depart.")
            if flight_count != "0":
                self.start_eco_campaign()
                time.sleep(1)
                button = count.find_element(By.XPATH, "..")
                self.driver.execute_script("arguments[0].click();", button)
                log(
                    f"✅ Departure action triggered for {flight_count} flight(s)."
                )
        except NoSuchElementException:
            log("Could not find departure elements.")

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
        if self.driver is None:
            log("Selenium driver is required to inspect consumable windows.")
            return

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
            log(f"Fuel price detected: {fuel_price_value}")

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
                log(f"CO2 price detected: {co2_price_value}")
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
        "--once",
        action="store_true",
        help="Run one cycle and exit instead of looping.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bot = AM4Bot(
        base_url=args.base_url,
        fuel_threshold=args.fuel_threshold,
        co2_threshold=args.co2_threshold,
        email=args.email,
        password=args.password,
        headless=args.headless,
    )

    try:
        bot.setup_driver()
        bot.ensure_logged_in()
        while True:
            bot.better_auto_price()
            bot.scan_consumables()
            bot.auto_depart_routine()
            if args.once:
                break
    except KeyboardInterrupt:
        log("Bot interrupted by user.")
    finally:
        bot.close_driver()

    return 0


if __name__ == "__main__":
    sys.exit(main())
