#!/usr/bin/env bash
# Headed Chromium for ATS application forms, driven by Core over MCP.
#
# HEADED, NOT HEADLESS, on purpose:
#  - anti-bot scoring (e.g. invisible reCAPTCHA v3) treats a real X-server
#    session far better than a trivially-fingerprinted headless one, and
#  - the noVNC port is the escape hatch: when a form needs an emailed code or a
#    human attestation, the operator opens the live desktop and finishes it by
#    hand instead of losing the filled-in form.
#
# Pipeline: Xvfb -> fluxbox -> x11vnc -> noVNC (websockify) -> Playwright MCP.
set -euo pipefail

: "${SCREEN_GEOMETRY:=1920x1080x24}"
: "${MCP_PORT:=8931}"
: "${VNC_PORT:=6080}"
: "${DISPLAY:=:99}"
export DISPLAY

log() { echo "[webmcp] $*" >&2; }

Xvfb "$DISPLAY" -screen 0 "$SCREEN_GEOMETRY" -nolisten tcp &
for _ in $(seq 1 50); do xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && break; sleep 0.2; done
log "Xvfb up on $DISPLAY ($SCREEN_GEOMETRY)"

fluxbox >/dev/null 2>&1 &

# -shared + -forever so the operator can attach mid-form and their disconnect
# does not tear the session down (which would lose the filled form).
x11vnc -display "$DISPLAY" -forever -shared -nopw -quiet -bg >/dev/null 2>&1
websockify --web /usr/share/novnc "$VNC_PORT" localhost:5900 >/dev/null 2>&1 &
log "noVNC on :$VNC_PORT"

# --isolated: no profile carried between sessions (an application form must
#   never inherit the previous company's cookie jar).
# --save-trace: a Playwright trace per session is the only record when a submit
#   silently fails.
exec npx -y @playwright/mcp@0.0.41 \
  --port "$MCP_PORT" \
  --host 0.0.0.0 \
  --browser chromium \
  --no-sandbox \
  --isolated \
  --viewport-size "1600,1000" \
  --save-trace \
  --output-dir /data/browser-artifacts \
  ${PW_EXTRA_ARGS:-}
