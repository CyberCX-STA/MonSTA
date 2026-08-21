#!/usr/bin/env bash
set -euo pipefail

# Config
XAMPP_VERSION="8.2.12"
XAMPP_INSTALLER="xampp-linux-x64-${XAMPP_VERSION}-0-installer.run"
XAMPP_URL="https://sourceforge.net/projects/xampp/files/XAMPP%20Linux/${XAMPP_VERSION}/${XAMPP_INSTALLER}/download"

DB_SQL="${1:-labrandor-database.sql}"
USERS_SQL="${2:-labrandor-sql-users.sql}"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/.venv"

# Checks
if [[ $EUID -eq 0 ]]; then
  echo "[!] Do not run this script directly as root. Run: bash install.sh"
  exit 1
fi

if [[ ! -f "$DB_SQL" ]]; then
  echo "[!] Missing database SQL file: $DB_SQL"
  exit 1
fi

if [[ ! -f "$USERS_SQL" ]]; then
  echo "[!] Missing users SQL file: $USERS_SQL"
  exit 1
fi

echo "[+] Installing OS packages..."
sudo apt update
sudo apt install -y ca-certificates curl wget python3 python3-pip python3-venv nodejs npm util-linux-extra mariadb-client-core

echo "[+] Installing Docker official repository..."
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true

echo "[+] Installing XAMPP. This make take a few moments..."
if [[ ! -x /opt/lampp/lampp ]]; then
  wget -4 -O "/tmp/$XAMPP_INSTALLER" "$XAMPP_URL"
  chmod +x "/tmp/$XAMPP_INSTALLER"
  sudo "/tmp/$XAMPP_INSTALLER" --mode unattended
else
  echo "[+] XAMPP already installed."
fi

echo "[+] Starting XAMPP..."
sudo /opt/lampp/lampp start

echo "[+] Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install \
  mysql-connector-python \
  docker \
  Jinja2 \
  fastapi \
  "starlette<1.0.0" \
  "uvicorn[standard]"

echo "[+] Installing Puppeteer..."
npm install puppeteer
npx puppeteer browsers install chrome

MYSQL="/opt/lampp/bin/mysql"

echo "[+] Importing Database SQL file..."
if [ -f "$DB_SQL" ]; then
  "$MYSQL" -u root < "$DB_SQL"
else
  echo "[!] Database SQL file not found: $DB_SQL"
fi
echo "[+] Importing Users SQL file..."
if [ -f "$USERS_SQL" ]; then
  "$MYSQL" -u root < "$USERS_SQL"
else
  echo "[!] Users SQL file not found: $USERS_SQL"
fi

echo "[+] Verifying Docker..."
docker --version || true

echo "[+] Adding $USER to Docker group..."
sudo usermod -aG docker "$USER"
echo "[!] Added $USER to Docker group."
echo "[!] Please log out and back in, or run: newgrp docker"

echo "[+] Warming the Docker cache..."
sg docker -c 'make warm-cache-all'

echo "[+] Install complete."
echo "[!] Log out and back in before using Docker without sudo, or run:"
echo "    newgrp docker"
echo "[+] Python venv: $VENV_DIR"
echo "[+] Activate with: source .venv/bin/activate"
