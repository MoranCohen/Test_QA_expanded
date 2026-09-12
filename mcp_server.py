"""
Ammeter QA MCP Server

Exposes tools for running tests, reading results, managing emulators,
and comparing runs. Connect via Claude Code, Claude Desktop, Cursor,
or any MCP-compatible client.

Setup:
    pip install mcp pytest-json-report

Claude Code (.claude/settings.json):
    {
      "mcpServers": {
        "ammeter-qa": {
          "command": "python",
          "args": ["/Users/morancohen/Downloads/Test_QA_expanded/mcp_server.py"]
        }
      }
    }

Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json):
    Same JSON block under "mcpServers".
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml
from mcp.server.mcpserver import MCPServer

PROJECT = Path(__file__).parent
RESULTS = PROJECT / "results"
CONFIG_FILE = PROJECT / "config" / "config.yaml"
JSON_REPORT = PROJECT / ".pytest_report.json"

EMULATOR_SCRIPTS = {
    "greenlee": "from Ammeters.Greenlee_Ammeter import GreenleeAmmeter; GreenleeAmmeter(5001).start_server()",
    "entes":    "from Ammeters.Entes_Ammeter import EntesAmmeter; EntesAmmeter(5002).start_server()",
    "circutor": "from Ammeters.Circutor_Ammeter import CircutorAmmeter; CircutorAmmeter(5003).start_server()",
}

# Track emulator subprocesses for the lifetime of this server process.
_emulator_procs: dict[str, subprocess.Popen] = {}

mcp = MCPServer("ammeter-qa")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@mcp.tool()
def run_tests(path: str = "tests/", markers: str = "") -> dict:
    """
    Run the pytest suite and return structured results.

    Args:
        path:    Test path or file, e.g. "tests/" or "tests/test_ammeters.py"
        markers: Optional pytest -m expression, e.g. "greenlee or entes"

    Returns:
        Dict with keys: passed, failed, errors, failures (list of nodeids), stdout, stderr
    """
    cmd = [
        sys.executable, "-m", "pytest", path,
        "--json-report", f"--json-report-file={JSON_REPORT}",
        "-q", "--tb=short",
    ]
    if markers:
        cmd += ["-m", markers]

    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT)

    report: dict = {}
    if JSON_REPORT.exists():
        report = json.loads(JSON_REPORT.read_text())

    summary = report.get("summary", {})
    failures = [
        t["nodeid"]
        for t in report.get("tests", [])
        if t.get("outcome") == "failed"
    ]

    return {
        "passed":   summary.get("passed", 0),
        "failed":   summary.get("failed", 0),
        "errors":   summary.get("errors", 0),
        "duration": summary.get("duration", None),
        "failures": failures,
        "stdout":   proc.stdout,
        "stderr":   proc.stderr,
    }


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@mcp.tool()
def list_results(subdir: str = "") -> list[str]:
    """
    List result files under the results/ directory.

    Args:
        subdir: Optional subdirectory, e.g. "data", "logs", "plots", "testing"
                Leave empty to list all subdirectories.

    Returns:
        List of relative file paths.
    """
    target = RESULTS / subdir if subdir else RESULTS
    if not target.exists():
        return []
    if target.is_file():
        return [str(target.relative_to(PROJECT))]
    return sorted(
        str(f.relative_to(PROJECT))
        for f in target.rglob("*")
        if f.is_file()
    )


@mcp.tool()
def read_result_file(relative_path: str) -> str:
    """
    Read the content of a result file.

    Args:
        relative_path: Path relative to project root, e.g. "results/data/run_01.json"

    Returns:
        File content as a string.
    """
    full = PROJECT / relative_path
    if not full.exists():
        return f"File not found: {relative_path}"
    return full.read_text()


@mcp.tool()
def compare_runs(file_a: str, file_b: str) -> dict:
    """
    Compare two result files line-by-line and surface differences.

    Args:
        file_a: Relative path to the baseline file.
        file_b: Relative path to the newer file.

    Returns:
        Dict with keys: added (lines in B not in A), removed (lines in A not in B).
    """
    def _read(p: str) -> list[str]:
        full = PROJECT / p
        return full.read_text().splitlines() if full.exists() else []

    lines_a = set(_read(file_a))
    lines_b = set(_read(file_b))

    return {
        "added":   sorted(lines_b - lines_a),
        "removed": sorted(lines_a - lines_b),
    }


# ---------------------------------------------------------------------------
# Emulators
# ---------------------------------------------------------------------------

@mcp.tool()
def start_emulator(name: str) -> str:
    """
    Start one of the ammeter emulators as a background process.

    Args:
        name: One of "greenlee" (port 5001), "entes" (port 5002), "circutor" (port 5003),
              or "all" to start all three.

    Returns:
        Status message.
    """
    targets = list(EMULATOR_SCRIPTS.keys()) if name == "all" else [name.lower()]
    unknown = [t for t in targets if t not in EMULATOR_SCRIPTS]
    if unknown:
        return f"Unknown emulator(s): {unknown}. Choose from: {list(EMULATOR_SCRIPTS.keys())} or 'all'."

    started = []
    already = []
    for t in targets:
        if t in _emulator_procs and _emulator_procs[t].poll() is None:
            already.append(t)
            continue
        proc = subprocess.Popen(
            [sys.executable, "-c", EMULATOR_SCRIPTS[t]],
            cwd=PROJECT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _emulator_procs[t] = proc
        started.append(t)

    parts = []
    if started:
        parts.append(f"Started: {started}")
    if already:
        parts.append(f"Already running: {already}")
    return " | ".join(parts)


@mcp.tool()
def stop_emulator(name: str) -> str:
    """
    Stop a running ammeter emulator.

    Args:
        name: One of "greenlee", "entes", "circutor", or "all".

    Returns:
        Status message.
    """
    targets = list(EMULATOR_SCRIPTS.keys()) if name == "all" else [name.lower()]
    stopped = []
    not_running = []

    for t in targets:
        proc = _emulator_procs.get(t)
        if proc and proc.poll() is None:
            proc.terminate()
            stopped.append(t)
        else:
            not_running.append(t)

    parts = []
    if stopped:
        parts.append(f"Stopped: {stopped}")
    if not_running:
        parts.append(f"Not running: {not_running}")
    return " | ".join(parts)


@mcp.tool()
def emulator_status() -> dict:
    """
    Check which emulators are currently running.

    Returns:
        Dict mapping emulator name → "running" | "stopped".
    """
    status = {}
    for name in EMULATOR_SCRIPTS:
        proc = _emulator_procs.get(name)
        status[name] = "running" if (proc and proc.poll() is None) else "stopped"
    return status


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@mcp.tool()
def get_config() -> dict:
    """
    Read and return the project configuration (config/config.yaml).

    Returns:
        Parsed config as a dict.
    """
    if not CONFIG_FILE.exists():
        return {"error": f"Config not found at {CONFIG_FILE}"}
    return yaml.safe_load(CONFIG_FILE.read_text())


if __name__ == "__main__":
    mcp.run()
