# Headhunter-WebMCP

The browser tool for [Headhunter](https://github.com/RevREB/Headhunter-Core):
a **headed Chromium exposed over MCP** that Core drives to fill and submit job
applications, with a **noVNC desktop** so a human can watch and take over when a
form needs an emailed code, a login, or a human attestation.

Not a dashboard — the Headhunter UI is served by Core. This service is purely
the browser Core calls as a tool.

## Why headed real Chromium

- Anti-bot scoring (invisible reCAPTCHA v3 etc.) treats a real X-server session
  far better than a fingerprintable headless one.
- The one control that catches silently-empty submits on React ATS forms is a
  **screenshot** of the filled field — a no-render engine can't produce it.

## Pipeline

`Xvfb -> fluxbox -> x11vnc -> noVNC (websockify) -> @playwright/mcp` (pinned).

| Port | Purpose |
|---|---|
| 8931 | MCP (streamable HTTP) — Core connects here to drive the browser |
| 6080 | noVNC — `kubectl -n headhunter port-forward svc/headhunter-webmcp 6080:6080` to watch/take over |

| Env | Default | Purpose |
|---|---|---|
| `MCP_PORT` | `8931` | MCP listen port |
| `VNC_PORT` | `6080` | noVNC listen port |
| `SCREEN_GEOMETRY` | `1920x1080x24` | virtual display size |
| `PW_EXTRA_ARGS` | — | extra flags passed to `@playwright/mcp` |

## License

MIT © 2026 RevREB. See [LICENSE](LICENSE).
