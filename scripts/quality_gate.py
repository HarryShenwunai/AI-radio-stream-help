"""One local/CI command for executable engineering checks; never deploys or connects accounts.

Install/check in one command: python scripts/quality_gate.py --bootstrap
Run without installation: python scripts/quality_gate.py [--full] [--test-python PATH]
The tool Python runs Ruff/mypy; --test-python may select a separate runtime test
environment. Full tests need app/requirements-core.txt, requirements-dev.txt,
and src/companion_runtime/connectors/requirements.txt. No model download needed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import venv

ROOT = Path(__file__).resolve().parents[1]


def bootstrap(arguments, test_python):
    """Explicit development-only installation, isolated from runtime Python."""
    directory = ROOT / ".build/quality-venv"
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(directory)
    expected = dict(line.strip().split("==", 1) for line in (ROOT / "requirements-quality.txt").read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#"))
    probe = subprocess.run([str(python), "-c", "import importlib.metadata,json; print(json.dumps({n:importlib.metadata.version(n) for n in ['ruff','mypy']}))"], capture_output=True, text=True)
    try:installed = json.loads(probe.stdout) if probe.returncode == 0 else {}
    except ValueError:installed = {}
    if installed != expected:
        pip = subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True)
        if pip.returncode:
            result = subprocess.run([str(python), "-m", "ensurepip"])
            if result.returncode:return result.returncode
        result = subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--index-url", "https://pypi.org/simple", "-r", str(ROOT / "requirements-quality.txt")])
        if result.returncode:return result.returncode
    forwarded = [value for value in arguments if value != "--bootstrap"]
    if not any(value == "--test-python" or value.startswith("--test-python=") for value in forwarded):
        forwarded.extend(["--test-python", test_python])
    return subprocess.run([str(python), str(Path(__file__).resolve()), *forwarded], cwd=ROOT).returncode


def source_hashes():
    paths = []
    for directory in ("app", "src", "scripts", "tests", "plugins", "desktop", "frontend", "assets", ".github", "review/formal-models"):
        for path in (ROOT / directory).rglob("*"):
            relative = path.relative_to(ROOT)
            if any(part in {"node_modules", "__pycache__", "test-results", "models", "voices", "data"} for part in relative.parts):
                continue
            image_source = (directory == 'assets' or relative.parts[:2] == ('app','static')) and path.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.svg','.avif'}
            if path.is_file() and (image_source or path.suffix in {".py", ".mjs", ".cjs", ".js", ".json", ".ps1", ".cmd", ".css", ".html", ".toml", ".yml", ".yaml", ".tla", ".cfg"} or path.name.startswith("requirements") and path.suffix == ".txt"):
                paths.append(path)
    paths.extend(ROOT / name for name in ("pyproject.toml", "requirements-quality.txt", "requirements-dev.txt"))
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(set(paths)) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", action="store_true", help="Explicitly install/reuse pinned tools in .build/quality-venv, then run checks")
    parser.add_argument("--full", action="store_true", help="Also execute Python HTTP/protocol and JavaScript UI/desktop regressions")
    parser.add_argument("--test-python", default=sys.executable, help="Python environment with application test dependencies")
    parser.add_argument("--report", type=Path, default=Path(os.environ.get("COMPANION_REPORT_DIR", str(ROOT / "review"))) / "quality-gate.json")
    args = parser.parse_args()
    if args.bootstrap:
        return bootstrap(sys.argv[1:], args.test_python)
    versions = {"python": sys.version.split()[0]}
    for name in ("ruff", "mypy"):
        try:versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name] = "MISSING: install requirements-quality.txt"
    commands = [
        ("critical-lint", [sys.executable, "-m", "ruff", "check", "app", "src", "scripts", "tests", "plugins", "desktop"]),
        ("strict-core-types", [sys.executable, "-m", "mypy", "--python-executable", args.test_python]),
        ("architecture", [sys.executable, "scripts/check_architecture.py"]),
        ("architecture-negative-fixtures", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_architecture_rules.py", "-v"]),
    ]
    if args.full:
        commands.extend([
            ("python-regression", [args.test_python, "scripts/check.py"]),
            ("desktop-python-regression", [args.test_python, "-m", "unittest", "discover", "-s", "desktop/test", "-p", "test_*.py", "-v"]),
            ("frontend-node-regression", ["node", "--test", *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "tests").glob("test_*.mjs"))]]),
            ("desktop-node-regression", ["node", "--test", *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "desktop/test").glob("*.test.cjs"))]]),
        ])
    args.report = args.report.resolve()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    log_dir = args.report.parent / (args.report.stem + "-logs")
    log_dir.mkdir(exist_ok=True)
    started = time.monotonic()
    started_at = dt.datetime.now(dt.timezone.utc)
    before = source_hashes()
    results = []
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), str(ROOT / "app"), environment.get("PYTHONPATH")]))
    environment["PYTHONUTF8"] = "1"
    environment["COMPANION_REPORT_DIR"] = str(args.report.parent)
    for name, command in commands:
        step = time.monotonic()
        print("Running " + name, flush=True)
        try:
            process = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            code, stdout, stderr = process.returncode, process.stdout, process.stderr
        except (OSError, subprocess.TimeoutExpired) as error:
            code, stdout, stderr = 124, "", str(error)
        log = log_dir / (name + ".txt")
        log.write_text(stdout + "\nSTDERR:\n" + stderr, encoding="utf-8")
        results.append({"name":name, "command":command, "exit_code":code, "passed":code == 0,
                        "elapsed_seconds":round(time.monotonic() - step, 3), "log":str(log),
                        "stdout_tail":stdout[-4000:], "stderr_tail":stderr[-8000:]})
        print(name + (": PASS" if code == 0 else ": FAIL (see " + str(log) + ")"), flush=True)
    after = source_hashes()
    unchanged = before == after
    changed_sources = {name:{"before":before.get(name), "after":after.get(name)}
                       for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)}
    regression = None
    if args.full:
        try:
            regression = json.loads((args.report.parent / "character-regression.json").read_text(encoding="utf-8"))
            if dt.datetime.fromisoformat(regression["observed_at"]) < started_at:
                regression = {"error":"Previous regression report is stale; inspect current subprocess exit code/log"}
        except (OSError, ValueError, KeyError, TypeError):regression = {"error":"Regression report unavailable; inspect subprocess exit code/log"}
    try:head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):head = "UNAVAILABLE"
    report = {"observed_at":dt.datetime.now(dt.timezone.utc).isoformat(), "passed":unchanged and all(step["passed"] for step in results),
              "full":args.full, "versions":versions, "source_commit":head, "source_sha256":after,
              "sources_unchanged_during_checks":unchanged, "sources_changed_during_checks":changed_sources, "checks":results,
              "python_regression":regression,
              "tool_version_sources":{"verified_on":"2026-11-12", "ruff":"https://pypi.org/pypi/ruff/json", "mypy":"https://pypi.org/pypi/mypy/json"},
              "elapsed_seconds":round(time.monotonic() - started, 3),
              "limits":["Strict typing covers the explicit pyproject core-module list, not all legacy server code", "AST contracts are bounded regression checks, not whole-program information-flow proof", "Local synthetic tests do not verify Windows/GPU hardware, real platform accounts or visual quality", "No deployment, downloads, account connection or messages are performed by this command"]}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(("PASS" if report["passed"] else "FAIL") + ": " + str(args.report), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
