#!/bin/bash
# Run CardPulse locally. Use this if "uvicorn" fails or port 8000 is in use.
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
  echo "Creating venv..."
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt
echo "Starting at http://127.0.0.1:8000 ..."
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
