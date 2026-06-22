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

## Termux / Proot Ubuntu setup

The bot can run in two Termux environments:

1. Native Termux with Chromium support
2. Termux using `proot-distro` Ubuntu when native Chromium is unavailable

### Option A: Native Termux

Run these commands in Termux:

```bash
pkg update && pkg upgrade -y
pkg install -y python git clang
pkg install -y chromium chromium-driver
```

Then install Python dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you want Playwright support too:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### Option B: Termux + Ubuntu via proot-distro

If your Termux build cannot run Chromium reliably, use a Ubuntu proot container.

```bash
pkg update && pkg upgrade -y
pkg install -y proot-distro
proot-distro install ubuntu
```

Then use the included helper script:

```bash
chmod +x run_termux_proot.sh
./run_termux_proot.sh
```

This helper:

- installs Ubuntu in `proot-distro` if needed
- installs Python 3, pip, Chromium, and ChromeDriver inside Ubuntu
- installs Python dependencies from `requirements.txt`
- installs Playwright Chromium if available

After the helper completes, run the bot in Ubuntu with:

```bash
python3 am4_bot.py --mode http --once --email your-email --password your-pass
```

If you want to enter Ubuntu manually instead of using the helper script:

```bash
proot-distro login ubuntu
cd /data/data/com.termux/files/home/Airlines-manager
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
python3 am4_bot.py --mode http --once --email your-email --password your-pass
```

### Browser mode vs HTTP-only mode

The bot supports these modes:

- `auto`: try Selenium, then Playwright, then Pyppeteer, then fall back to HTTP-only
- `selenium`: force Selenium only
- `playwright`: force Playwright only
- `pyppeteer`: force Pyppeteer only
- `http`: requests-only mode (no browser automation)

Use HTTP-only mode when Chromium is unavailable or when you want a lighter Termux setup. In HTTP-only mode, the bot can still:

- log in via requests
- read bank balance
- check departures via API endpoints
- parse fuel and CO2 pages

Example HTTP-only command:

```bash
python am4_bot.py --mode http --once --headless --email your-email --password your-pass
```

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
