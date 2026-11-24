#!/usr/bin/env bash
# Start the mock SOAP DMS and the Streamlit inspector UI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

STREAMLIT_PORT="${ERPBRIDGE_UI_PORT:-8505}"
SOAP_PORT="${ERPBRIDGE_SOAP_PORT:-8005}"
SOAP_HOST="${ERPBRIDGE_SOAP_HOST:-127.0.0.1}"
DATA="$ROOT/data"
mkdir -p "$DATA"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

wait_port() {
  local port="$1"
  local tries=80
  local i=0
  while ! python3 -c "import socket; s=socket.create_connection(('127.0.0.1', $port), 0.4); s.close()" 2>/dev/null; do
    i=$((i + 1))
    if (( i >= tries )); then
      echo "Timed out waiting for port $port" >&2
      exit 1
    fi
    sleep 0.25
  done
}

cleanup() {
  if [[ -n "${SOAP_PID:-}" ]] && kill -0 "$SOAP_PID" 2>/dev/null; then
    kill "$SOAP_PID" 2>/dev/null || true
  fi
  rm -f "$DATA/soap.pid"
}
trap cleanup EXIT INT TERM

export ERPBRIDGE_SOAP_PORT="$SOAP_PORT"
export ERPBRIDGE_SOAP_HOST="$SOAP_HOST"
export ERPBRIDGE_SOAP_URL="http://${SOAP_HOST}:${SOAP_PORT}/dms"
export ERPBRIDGE_UI_PORT="$STREAMLIT_PORT"

echo "Starting mock SOAP DMS on http://${SOAP_HOST}:${SOAP_PORT}/dms …"
.venv/bin/python -m erpbridge serve-soap --host "$SOAP_HOST" --port "$SOAP_PORT" \
  >"$DATA/soap.log" 2>&1 &
SOAP_PID=$!
echo "$SOAP_PID" >"$DATA/soap.pid"
wait_port "$SOAP_PORT"
if ! kill -0 "$SOAP_PID" 2>/dev/null; then
  echo "Mock SOAP DMS failed to start. Tail of data/soap.log:" >&2
  tail -n 40 "$DATA/soap.log" >&2
  exit 1
fi

echo
echo "MCP-to-ERP Bridge is ready."
echo "  UI:      http://127.0.0.1:${STREAMLIT_PORT}"
echo "  SOAP:    http://${SOAP_HOST}:${SOAP_PORT}/dms"
echo "  WSDL:    http://${SOAP_HOST}:${SOAP_PORT}/dms?wsdl"
echo "  Demo:    .venv/bin/python -m erpbridge demo"
echo "  Stdio:   .venv/bin/python -m erpbridge stdio"
echo

exec .venv/bin/streamlit run app.py --server.headless true --server.port "$STREAMLIT_PORT" --server.address 127.0.0.1
