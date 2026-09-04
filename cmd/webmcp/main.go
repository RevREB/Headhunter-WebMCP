// Command webmcp serves the Headhunter dashboard and a thin MCP surface, both
// backed entirely by the Headhunter-Core API (CORE_URL). It holds no state of
// its own — Core is the single source of truth.
package main

import (
	"embed"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
)

//go:embed web/index.html
var webFS embed.FS

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	addr := env("LISTEN_ADDR", ":3000")
	coreURL := env("CORE_URL", "http://headhunter-core.career-ops.svc.cluster.local:8080")
	core, err := url.Parse(coreURL)
	if err != nil {
		log.Fatalf("bad CORE_URL %q: %v", coreURL, err)
	}

	proxy := httputil.NewSingleHostReverseProxy(core)
	mux := http.NewServeMux()

	// dashboard
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		b, _ := webFS.ReadFile("web/index.html")
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(b)
	})

	// the dashboard reads the Core API through this reverse proxy
	mux.Handle("/api/", proxy)

	// thin MCP surface: mirror Core's tool manifest.
	// TODO(phase-3): serve the full MCP protocol via
	// github.com/modelcontextprotocol/go-sdk, proxying tool calls to Core.
	mux.HandleFunc("/mcp/tools", func(w http.ResponseWriter, _ *http.Request) {
		resp, err := http.Get(coreURL + "/api/tools")
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.Copy(w, resp.Body)
	})

	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok\n"))
	})

	log.Printf("webmcp listening on %s (core=%s)", addr, coreURL)
	log.Fatal(http.ListenAndServe(addr, mux))
}
