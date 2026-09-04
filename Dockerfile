# syntax=docker/dockerfile:1
# Headhunter-WebMCP: a headed Chromium exposed over MCP (for Core to drive job
# applications) with a noVNC desktop (for a human to watch and take over).
#
# Real Chromium, not a lightweight engine: ATS forms are React-heavy, and the
# one control that catches silently-empty submits is a SCREENSHOT of the filled
# field — which a no-render engine cannot produce. Chromium is the floor.
FROM mcr.microsoft.com/playwright:v1.62.1-noble

ENV DEBIAN_FRONTEND=noninteractive
# upgrade patches the base's stale packages (clears fixable CVEs); the desktop
# stack installs in the same layer; all apt cruft is purged so none of it ships.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
      xvfb x11vnc novnc websockify fluxbox tini ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Pin the MCP server so tool names never shift under a running agent.
RUN npm install -g @playwright/mcp@0.0.41 && npm cache clean --force

# @playwright/mcp resolves Chromium by its own playwright-core revision, not the
# base's — pre-install the matching build, then drop the browsers we never launch.
RUN npx -y playwright@1.56.0-alpha-2025-10-01 install chromium \
 && rm -rf /ms-playwright/firefox-* /ms-playwright/webkit-* \
 && npm cache clean --force \
 && rm -rf /root/.npm /root/.cache

WORKDIR /srv
COPY entrypoint.sh /srv/entrypoint.sh
RUN chmod +x /srv/entrypoint.sh

# 8931 = MCP (streamable HTTP) for Core; 6080 = noVNC for a human to take over.
EXPOSE 8931 6080
ENTRYPOINT ["/usr/bin/tini", "--", "/srv/entrypoint.sh"]
