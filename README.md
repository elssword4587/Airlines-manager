# Airlines Manager AM4 Bot (Python)

This repository contains a Python version of the AM4 automation logic from the Tampermonkey script you provided. The goal is to run the same core behaviors in a Python environment such as Termux, using Selenium for browser interaction and requests for direct HTTP actions.

## What this script does

- Watches the route pricing panel and tries to improve auto-price inputs.
- Starts the eco-friendly campaign before departure.
- Checks whether flights are ready to depart.
- Buys fuel and CO2 when the price is at or below the configured thresholds.

## Termux setup

Install the required packages:

```bash
pkg update && pkg upgrade
pkg install python git clang
pkg install chromium chromium-driver
```

Then install Python dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration

You can set the values either in the environment or via command-line flags:

- `AM4_BASE_URL` (default: `https://www.airlinemanager.com`)
- `AM4_EMAIL` (optional email for automatic login)
- `AM4_PASSWORD` (optional password for automatic login)
- `AM4_FUEL_THRESHOLD` (default: `550`)
- `AM4_CO2_THRESHOLD` (default: `125`)

Example:

```bash
export AM4_BASE_URL="https://www.airlinemanager.com"
export AM4_EMAIL="your-email@example.com"
export AM4_PASSWORD="your-password"
export AM4_FUEL_THRESHOLD=550
export AM4_CO2_THRESHOLD=125
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

Run in headless mode if your browser setup supports it:

```bash
python am4_bot.py --headless
```

## Notes

- The website structure may change, so some selectors may need adjustment.
- You should log in to the game once first and keep the session active.
- This script is a Python translation of the original logic; it is not a literal browser extension port.

## Files

- [am4_bot.py](am4_bot.py) - main bot logic
- [requirements.txt](requirements.txt) - Python dependencies
- [.env.example](.env.example) - sample environment variables
- [.gitignore](.gitignore) - ignore local config and cache files
