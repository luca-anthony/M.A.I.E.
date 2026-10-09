#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

sudo apt update
sudo apt install -y python3-venv python3-pip python3-picamera2 libportaudio2 libsndfile1 espeak-ng poppler-utils git curl

if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pi.txt

mkdir -p models/piper
(cd models/piper && python -m piper.download_voices en_US-lessac-medium)

ollama pull gemma3:4b

if [ ! -f .env ]; then
  cp .env.example .env
fi

echo "Setup finished. Run: . .venv/bin/activate && python main.py --mode local"
