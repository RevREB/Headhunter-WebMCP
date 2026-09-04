# Headhunter-WebMCP

The dashboard and MCP surface for [Headhunter](https://github.com/RevREB/Headhunter-Core).
Stateless: everything is read from and written through the **Headhunter-Core**
API (`CORE_URL`). This is the Gen1 scaffold — a minimal dashboard plus a thin
tool-manifest passthrough — that grows toward full feature parity over Phase 3.

## What it does

- Serves a minimal dashboard (`/`) that lists the tools exposed by Core.
- Reverse-proxies `/api/*` to Core.
- `/mcp/tools` mirrors Core's tool manifest. The full MCP protocol (tool calls
  over streamable HTTP) will be served via the official Go MCP SDK in Phase 3.

## Configuration

| Env | Default | Purpose |
|---|---|---|
| `LISTEN_ADDR` | `:3000` | listen address |
| `CORE_URL` | `http://headhunter-core.career-ops.svc.cluster.local:8080` | Headhunter-Core API |

## License

MIT © 2026 RevREB. See [LICENSE](LICENSE).
