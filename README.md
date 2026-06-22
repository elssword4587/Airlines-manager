# Airlines Manager AM4 Bot (Python)

This repository contains a Python version of the AM4 automation logic from the Tampermonkey script you provided. The goal is to run the same core behaviors in a Python environment such as Termux, using Selenium for browser interaction and requests for direct HTTP actions.

## What this script does

- Watches the route pricing panel and tries to improve auto-price inputs.
- Starts the eco-friendly campaign before departure.
- Checks whether flights are ready to depart.
- Buys fuel and CO2 when the price is at or below the configured thresholds.

## Clone the repository

```bash
git clone https://github.com/elssword4587/Airlines-manager
cd Airlines-manager
```

## Termux setup

Install the required packages:

```bash
pkg update && pkg upgrade
pkg install python git clang
pkg install chromium chromium-driver
```

If your Termux build does not provide a usable Chromium binary, you can also try a proot/Ubuntu-based setup and install Chromium there instead.

Then install Python dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you added `playwright` to `requirements.txt`, install the Playwright browsers after pip:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install --with-deps
```

If Chromium is still not working, the bot can still perform HTTP-based checks such as login, bank balance, and fuel page parsing, but browser-dependent actions may be limited.

## Configuration

You can set the values either in the environment or via command-line flags:

- `AM4_BASE_URL` (default: `https://www.airlinemanager.com`)
- `AM4_EMAIL` (optional email for automatic login)
- `AM4_PASSWORD` (optional password for automatic login)
- `AM4_FUEL_THRESHOLD` (default: `550`)
- `AM4_CO2_THRESHOLD` (default: `125`)
- `AM4_DEPART_CHECK_INTERVAL_MINUTES` (default: `5`)
- `AM4_FUEL_CHECK_INTERVAL_MINUTES` (default: `1`)
- `AM4_DEPART_CHECK_INTERVAL_MIN_SECONDS` / `AM4_DEPART_CHECK_INTERVAL_MAX_SECONDS` (optional random depart range in seconds)
- `AM4_FUEL_CHECK_INTERVAL_MIN_SECONDS` / `AM4_FUEL_CHECK_INTERVAL_MAX_SECONDS` (optional random fuel range in seconds)

Example:

```bash
export AM4_BASE_URL="https://www.airlinemanager.com"
export AM4_EMAIL="your-email@example.com"
export AM4_PASSWORD="your-password"
export AM4_FUEL_THRESHOLD=550
export AM4_CO2_THRESHOLD=125
export AM4_DEPART_CHECK_INTERVAL_MINUTES=5
export AM4_FUEL_CHECK_INTERVAL_MINUTES=1
export AM4_DEPART_CHECK_INTERVAL_MIN_SECONDS=1000
export AM4_DEPART_CHECK_INTERVAL_MAX_SECONDS=5000
export AM4_FUEL_CHECK_INTERVAL_MIN_SECONDS=600
export AM4_FUEL_CHECK_INTERVAL_MAX_SECONDS=1800
```

## Running the bot

Run once for a single cycle:

```bash
python am4_bot.py --once
```

Run continuously:

```bash
python am4_bot.py
```

You can override the loop intervals if you want faster or slower checks:

```bash
python am4_bot.py --depart-check-interval-minutes 3 --fuel-check-interval-minutes 0.5
```

If you want the bot to keep using the saved `.env` range settings, you can run:

```bash
python am4_bot.py --change-interval
```

If you want the bot to pick a random delay inside a range for each check, set the values once in `.env` or use the interactive helper:

```bash
python am4_bot.py --configure-intervals
```

This will ask for four values:
- depart min (seconds)
- depart max (seconds)
- fuel min (seconds)
- fuel max (seconds)

You can also pass them directly on the command line:

```bash
python am4_bot.py \
  --depart-check-interval-min-seconds 1000 \
  --depart-check-interval-max-seconds 5000 \
  --fuel-check-interval-min-seconds 600 \
  --fuel-check-interval-max-seconds 1800
```

Run in headless mode if your browser setup supports it:

```bash
python am4_bot.py --headless
```

Modes
 - `auto`: try Selenium, then Playwright, then Pyppeteer, then fall back to HTTP-only.
 - `selenium`: force Selenium-only (will not try Playwright/Pyppeteer).
 - `playwright`: force Playwright for browser automation.
 - `pyppeteer`: force Pyppeteer for browser automation.
 - `http`: use requests-only mode (no browser automation).

Example (HTTP-only):

```bash
python am4_bot.py --mode http --once --headless --email your-email --password your-pass
```

## Notes

- The website structure may change, so some selectors may need adjustment.
- You should log in to the game once first and keep the session active.
- Browser-dependent actions require a working Chromium/Chrome runtime.
- This script is a Python translation of the original logic; it is not a literal browser extension port.

## Files

- [am4_bot.py](am4_bot.py) - main bot logic
- [requirements.txt](requirements.txt) - Python dependencies
- [.env.example](.env.example) - sample environment variables
- [.gitignore](.gitignore) - ignore local config and cache files
