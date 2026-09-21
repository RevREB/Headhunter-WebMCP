"""Static contract tests for Headhunter-WebMCP.

This repo ships no application code: it is a Dockerfile plus an entrypoint that
wires Xvfb -> fluxbox -> x11vnc -> noVNC -> @playwright/mcp, and a README that
tells an operator which knobs exist. The failure mode that actually bites is
DRIFT between those three files -- a pin bumped in one place and not the other,
a port exposed that nothing listens on, a documented env var that no longer
does anything. That is what these tests pin down.

They are static assertions only. Proof that the container actually starts and
serves MCP lives in test/mcp_smoke.py, which runs against a built image in CI.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text()
ENTRYPOINT = (ROOT / "entrypoint.sh").read_text()
README = (ROOT / "README.md").read_text()

MCP_PKG_RE = re.compile(r"@playwright/mcp@([0-9A-Za-z.+-]+)")
ENTRY_DEFAULT_RE = re.compile(r'^:\s*"\$\{(\w+):=([^}]*)\}"', re.MULTILINE)
README_ENV_ROW_RE = re.compile(r"^\|\s*`(\w+)`\s*\|\s*(.*?)\s*\|", re.MULTILINE)


def entrypoint_defaults():
    return dict(ENTRY_DEFAULT_RE.findall(ENTRYPOINT))


def readme_env_table():
    """{VAR: documented default}. The README env table is the only table whose
    first column is a backticked identifier, so the row regex is unambiguous."""
    rows = {}
    for name, default in README_ENV_ROW_RE.findall(README):
        rows[name] = default.strip("` ")
    return rows


class PlaywrightMcpPin(unittest.TestCase):
    """The Dockerfile comment states the reason out loud: 'Pin the MCP server so
    tool names never shift under a running agent.' The pin only holds if the
    version baked into the image is the version the entrypoint actually execs --
    otherwise npx silently resolves a different build at container start."""

    def test_dockerfile_pins_an_exact_version(self):
        versions = MCP_PKG_RE.findall(DOCKERFILE)
        self.assertTrue(versions, "Dockerfile installs no @playwright/mcp")
        for v in versions:
            self.assertRegex(
                v, r"^\d+\.\d+\.\d+", f"@playwright/mcp@{v} is not an exact pin"
            )

    def test_entrypoint_execs_the_version_the_image_baked_in(self):
        baked = set(MCP_PKG_RE.findall(DOCKERFILE))
        run = set(MCP_PKG_RE.findall(ENTRYPOINT))
        self.assertTrue(run, "entrypoint.sh never invokes @playwright/mcp")
        self.assertEqual(
            baked,
            run,
            "Dockerfile bakes @playwright/mcp"
            f"{sorted(baked)} but entrypoint runs {sorted(run)}; "
            "npx would download a different build at runtime",
        )


class PortsAndEnv(unittest.TestCase):
    def test_exposed_ports_are_the_ports_the_entrypoint_listens_on(self):
        exposed = set()
        for line in DOCKERFILE.splitlines():
            if line.startswith("EXPOSE"):
                exposed.update(line.split()[1:])
        d = entrypoint_defaults()
        listening = {d.get("MCP_PORT"), d.get("VNC_PORT")}
        self.assertEqual(
            exposed, listening, "EXPOSE does not match the entrypoint's listen ports"
        )

    def test_every_documented_env_var_is_read_by_the_entrypoint(self):
        for name in readme_env_table():
            self.assertIn(
                name,
                ENTRYPOINT,
                f"README documents {name} but entrypoint.sh never reads it",
            )

    def test_documented_defaults_match_the_entrypoint(self):
        defaults = entrypoint_defaults()
        for name, documented in readme_env_table().items():
            if documented in ("", "-", "--", "—"):  # em dash == no default
                continue
            if name not in defaults:
                continue
            self.assertEqual(
                defaults[name],
                documented,
                f"{name}: entrypoint defaults to {defaults[name]!r}, "
                f"README says {documented!r}",
            )


class EntrypointInvariants(unittest.TestCase):
    def test_strict_mode(self):
        self.assertIn(
            "set -euo pipefail",
            ENTRYPOINT,
            "entrypoint must abort on the first failed stage, not limp on with "
            "half a pipeline up",
        )

    def test_requests_the_only_browser_the_image_ships(self):
        """The image deletes firefox and webkit to keep the layer small, so the
        entrypoint asking for anything but chromium is an instant crash-loop."""
        self.assertRegex(
            ENTRYPOINT,
            r"--browser\s+chromium",
            "entrypoint must launch chromium: the image ships no other browser",
        )
        self.assertRegex(DOCKERFILE, r"rm -rf /ms-playwright/firefox-")

    def test_sessions_are_isolated(self):
        """A job application form must never inherit the previous company's
        cookie jar; --isolated is what enforces that."""
        self.assertIn("--isolated", ENTRYPOINT)

    def test_traces_are_written_under_the_data_mount(self):
        """--save-trace is the only record when an ATS submit silently fails;
        it has to land somewhere the pod actually persists."""
        self.assertIn("--save-trace", ENTRYPOINT)
        self.assertRegex(ENTRYPOINT, r"--output-dir\s+/data/")


class Workflows(unittest.TestCase):
    def test_workflow_files_parse(self):
        yaml = __import__("yaml")
        wf_dir = ROOT / ".github" / "workflows"
        files = sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
        self.assertTrue(files, "no workflows found")
        for f in files:
            with self.subTest(workflow=f.name):
                doc = yaml.safe_load(f.read_text())
                self.assertIsInstance(doc, dict)
                # PyYAML parses a bare `on:` key as the boolean True.
                self.assertTrue(
                    "on" in doc or True in doc, f"{f.name} declares no triggers"
                )
                self.assertIn("jobs", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
