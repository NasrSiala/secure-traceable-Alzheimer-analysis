#!/usr/bin/env bash
# Does SIGTERM to fabric/gateway-serve.sh (what test_no_phi_onchain.py sends with
# Popen.terminate()) stop the gateway it started? The host-Node branch is run for real with a
# stub `npm` whose `run start` stays up like the gateway; the shared library is the real one.
# Usage: orphan-probe.sh <repo root>   (run it on Linux: signals differ under MSYS)
set -u
repo=$1
work=$(mktemp -d)
mkdir -p "$work/fabric/lib" "$work/fabric/wallet" "$work/ledger-gateway/node_modules/typescript" \
  "$work/bin" "$work/tokens"
cp "$repo/fabric/gateway-serve.sh" "$work/fabric/"
cp "$repo/fabric/lib/gateway-run.sh" "$work/fabric/lib/"
touch "$work/fabric/wallet/peer0-org1-tls-ca.crt"
echo '{"agent-ingestion":"x"}' > "$work/tokens/tokens.json"
printf '#!/bin/sh\nexit 0\n' > "$work/bin/node"
cat > "$work/bin/npm" <<'STUB'
#!/bin/sh
# `npm run build` returns; `npm run start` stays up, as the gateway does, and records its pid.
if [ "$2" = start ]; then
  sleep 300 &
  echo $! > "$STUB_PIDFILE"
  wait
fi
exit 0
STUB
chmod +x "$work/bin/node" "$work/bin/npm"
export PATH="$work/bin:$PATH" STUB_PIDFILE="$work/gateway.pid"
GATEWAY_SERVE_TOKEN_DIR="$work/tokens" GATEWAY_SERVE_PORT=18080 \
  bash "$work/fabric/gateway-serve.sh" >/dev/null 2>&1 &
serve=$!
for _ in $(seq 1 50); do [ -s "$STUB_PIDFILE" ] && break; sleep 0.2; done
gateway=$(cat "$STUB_PIDFILE" 2>/dev/null || echo "")
echo "serve script pid=$serve, gateway pid=${gateway:-none}"
kill -TERM "$serve"
sleep 1
if [ -n "$gateway" ] && kill -0 "$gateway" 2>/dev/null; then
  echo "RESULT: the gateway is still running after SIGTERM to the script (orphan)"
  kill "$gateway" 2>/dev/null
  status=1
else
  echo "RESULT: the gateway stopped with the script"
  status=0
fi
rm -rf "$work"
exit $status
