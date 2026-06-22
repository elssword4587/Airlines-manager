#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(pwd)"

if ! command -v proot-distro >/dev/null 2>&1; then
  echo "ERROR: proot-distro is not installed. Install it in Termux first."
  echo "Example: pkg install proot-distro"
  exit 1
fi

if ! proot-distro list | grep -q '^ubuntu'; then
  echo "Installing Ubuntu distro into proot-distro..."
  proot-distro install ubuntu
fi

cat <<'EOF'
========================================
Launching Ubuntu proot environment and preparing the AM4 bot.
If prompted, allow any package installs.
========================================
EOF

proot-distro login ubuntu -- bash -lc "
set -euo pipefail
apt update
apt install -y python3 python3-pip chromium chromium-browser chromium-chromedriver || apt install -y python3 python3-pip chromium-browser chromium-chromedriver
cd '${REPO_DIR}'
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium || true
printf '\nDone. Run the bot with:\n'
printf '  python3 am4_bot.py --mode http --once --email YOUR_EMAIL --password YOUR_PASSWORD\n'
"
