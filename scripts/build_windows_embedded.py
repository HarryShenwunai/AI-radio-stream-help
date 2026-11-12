"""Assemble official Windows Python and Windows wheels on any build host.

This does not compile or execute Windows code. Misaki 0.9.4 declares Python
<3.13; including it on this interpreter requires an explicit compatibility-
experiment flag and is recorded as unsupported by upstream, without changing
its metadata. Wine testing is a separate, non-native validation step.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version, InvalidVersion

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = "3.13.17"
PYTHON_MINOR = (3, 13)
PYTHON_URL = "https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip"
PYTHON_SHA256 = "9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38"
LLAMA_URL = "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.36/llama_cpp_python-0.3.36-py3-none-win_amd64.whl"
LLAMA_SHA256 = "ae5e88a2cf464e5a2dde7c8898c2d5c71cc24d03cac6396bf7509456bde0b9fb"
ROOT_REQUIREMENTS = ["Pillow==13.0.0", "llama-cpp-python==0.3.36", "kokoro-onnx==0.6.1", "misaki[zh]==0.9.4"]
ENV = default_environment()
ENV.update({"python_version": "3.13", "python_full_version": PYTHON_VERSION,
            "implementation_version": PYTHON_VERSION, "sys_platform": "win32",
            "os_name": "nt", "platform_system": "Windows", "platform_machine": "AMD64",
            "platform_release": "10", "platform_version": "10.0.19045",
            "platform_python_implementation": "CPython", "implementation_name": "cpython"})
TAGS = list(cpython_tags(PYTHON_MINOR, abis=["cp313"], platforms=["win_amd64"]))
TAGS += list(compatible_tags(PYTHON_MINOR, interpreter="cp313", platforms=["win_amd64"]))
RANK = {tag: index for index, tag in enumerate(TAGS)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Companion-Windows-Assembler/1"}), timeout=45) as response:
        return json.load(response)


def download(url: str, expected: str, cache: Path) -> Path:
    name = PurePosixPath(urllib.request.urlparse(url).path).name if hasattr(urllib.request, "urlparse") else url.rsplit("/", 1)[-1]
    # URL path is official metadata, but still cannot select an arbitrary cache path.
    if not re.fullmatch(r"[A-Za-z0-9_.+%-]+", name):
        raise ValueError("unsafe download filename")
    target = cache / name
    if target.is_file() and sha256(target) == expected:
        return target
    part = target.with_suffix(target.suffix + ".part")
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Companion-Windows-Assembler/1"}), timeout=90) as response, part.open("wb") as stream:
                shutil.copyfileobj(response, stream, 1024 * 1024)
            actual = sha256(part)
            if actual != expected:
                raise ValueError("download SHA256 mismatch: " + name)
            part.replace(target)
            print("downloaded " + name, flush=True)
            return target
        except (OSError, ValueError) as error:
            last_error = error
            part.unlink(missing_ok=True)
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError("download failed: " + name) from last_error


def wheel_rank(filename: str) -> int | None:
    try:
        _, _, _, tags = parse_wheel_filename(filename)
    except ValueError:
        return None
    values = [RANK[tag] for tag in tags if tag in RANK]
    return min(values) if values else None


def choose(name: str, specifier: SpecifierSet, allow_experiment: bool) -> dict:
    current = fetch_json("https://pypi.org/pypi/" + name + "/json")
    versions = []
    for raw_version in current["releases"]:
        try:
            value = Version(raw_version)
        except InvalidVersion:
            continue
        if not value.is_prerelease:
            versions.append(value)
    versions.sort(reverse=True)
    for version in versions:
        if not specifier.contains(version):
            continue
        metadata = current if str(version) == current["info"]["version"] else fetch_json(f"https://pypi.org/pypi/{name}/{version}/json")
        requires_python = metadata["info"].get("requires_python") or ""
        python_allowed = not requires_python or SpecifierSet(requires_python).contains(PYTHON_VERSION)
        experimental = name == "misaki" and str(version) == "0.9.4" and allow_experiment
        if not python_allowed and not experimental:
            continue
        files = [item for item in metadata["urls"] if not item.get("yanked")]
        if name == "llama-cpp-python" and str(version) == "0.3.36":
            selected = {"filename": LLAMA_URL.rsplit("/", 1)[-1], "url": LLAMA_URL,
                        "sha256": LLAMA_SHA256, "source": "official GitHub CPU release"}
        else:
            candidates = [(wheel_rank(item["filename"]), item) for item in files if item["filename"].endswith(".whl")]
            candidates = [(rank, item) for rank, item in candidates if rank is not None]
            if candidates:
                _, item = min(candidates, key=lambda pair: pair[0])
                selected = {"filename": item["filename"], "url": item["url"], "sha256": item["digests"]["sha256"], "source": "PyPI wheel"}
            elif name == "jieba" and str(version) == "0.42.1":
                item = next(x for x in files if x["filename"] == "jieba-0.42.1.tar.gz")
                selected = {"filename": item["filename"], "url": item["url"], "sha256": item["digests"]["sha256"], "source": "PyPI pure-Python source; build pure wheel on host"}
            else:
                continue
        return {"name": name, "version": str(version), "requires_python": requires_python,
                "requires_dist": metadata["info"].get("requires_dist") or [],
                "declared_python_supported": python_allowed,
                "compatibility_experiment": bool(experimental and not python_allowed), **selected}
    raise RuntimeError(f"No official compatible Windows/Python wheel for {name}{specifier}")


def resolve(allow_experiment: bool) -> list[dict]:
    if not allow_experiment:
        raise RuntimeError("Misaki 0.9.4 declares Python<3.13; use --allow-misaki-313-experiment only for explicit compatibility testing")
    constraints: dict[str, list[str]] = {}
    extras: dict[str, set[str]] = {}
    selected: dict[str, dict] = {}
    expanded: dict[str, tuple] = {}
    pending = [Requirement(value) for value in ROOT_REQUIREMENTS]
    while pending:
        req = pending.pop(0)
        name = canonicalize_name(req.name)
        specs = constraints.setdefault(name, [])
        if str(req.specifier) not in specs:
            specs.append(str(req.specifier))
        extras.setdefault(name, set()).update(req.extras)
        combined = SpecifierSet(",".join(filter(None, specs)))
        chosen = selected.get(name)
        if chosen is None or not combined.contains(chosen["version"]):
            chosen = choose(name, combined, allow_experiment)
            selected[name] = chosen
            print(f"resolved {name}=={chosen['version']} ({chosen['source']})", flush=True)
        identity = (chosen["version"], tuple(sorted(extras[name])))
        if expanded.get(name) == identity:
            continue
        expanded[name] = identity
        for raw in chosen["requires_dist"]:
            dependency = Requirement(raw)
            if dependency.marker is not None and not any(dependency.marker.evaluate({**ENV, "extra": extra}) for extra in extras[name] | {""}):
                continue
            pending.append(dependency)
    return list(selected.values())


def member_target(name: str, base: Path) -> Path:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("unsafe archive path")
    return base.joinpath(*path.parts)


def unpack_archive(path: Path, destination: Path, wheel: bool = False) -> None:
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("archive symbolic link")
            parts = PurePosixPath(entry.filename).parts
            if wheel and parts and parts[0].endswith(".data"):
                if len(parts) < 3 or parts[1] not in {"purelib", "platlib"}:
                    # Console scripts/headers are not needed by this application.
                    continue
                name = "/".join(parts[2:])
            else:
                name = entry.filename
            target = member_target(name, destination)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))


def build_jieba(source: Path, cache: Path) -> Path:
    # The only allowed source build is the official pure-Python jieba release.
    with tarfile.open(source, "r:gz") as archive:
        names = archive.getnames()
        if any(PurePosixPath(name).suffix.lower() in {".so", ".pyd", ".dll", ".dylib", ".c", ".cpp", ".cxx"} for name in names):
            raise RuntimeError("jieba source unexpectedly contains native code")
        setup = archive.extractfile("jieba-0.42.1/setup.py").read().decode("utf-8")
        if "Extension(" in setup or "ext_modules" in setup:
            raise RuntimeError("jieba source unexpectedly declares extension modules")
    output = cache / "pure-wheels"
    output.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--no-index", "--wheel-dir", str(output), str(source)], check=True)
    built = next(output.glob("jieba-0.42.1-*-none-any.whl"))
    return built


def inspect_windows_binaries(site: Path) -> list[dict]:
    result = []
    for path in sorted(site.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".so", ".dylib"}:
            raise RuntimeError("non-Windows binary in target: " + str(path))
        if path.suffix.lower() not in {".dll", ".pyd", ".exe"}:
            continue
        data = path.read_bytes()
        if data[:2] != b"MZ" or len(data) < 64:
            raise RuntimeError("invalid PE binary: " + str(path))
        offset = struct.unpack_from("<I", data, 0x3c)[0]
        if data[offset:offset + 4] != b"PE\0\0" or struct.unpack_from("<H", data, offset + 4)[0] != 0x8664:
            raise RuntimeError("target binary is not Windows x64: " + str(path))
        result.append({"path": str(path.relative_to(site)), "machine": "AMD64", "sha256": hashlib.sha256(data).hexdigest()})
    return result


def copy_sources(output: Path) -> None:
    (output / "app").mkdir(exist_ok=True)
    for name in ["server.py", "models-manifest.json", "model-sources.json", "LICENSE", "ATTRIBUTIONS.md"]:
        source = ROOT / "app" / name
        if source.exists():
            shutil.copyfile(source, output / "app" / name)
    shutil.copytree(ROOT / "app/static", output / "app/static", dirs_exist_ok=True)
    shutil.copytree(ROOT / "src/companion_runtime", output / "src/companion_runtime", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if (ROOT / "app/licenses").is_dir():
        shutil.copytree(ROOT / "app/licenses", output / "app/licenses", dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".build/windows-embedded-backend")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/windows-embedded")
    parser.add_argument("--allow-misaki-313-experiment", action="store_true")
    parser.add_argument("--lock", type=Path, help="Reuse URLs, versions and hashes from a previously generated manifest")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    if args.lock:
        lock = json.loads(args.lock.read_text())
        packages = lock["packages"]
        if lock["python"]["version"] != PYTHON_VERSION or lock["python"]["sha256"] != PYTHON_SHA256:
            raise ValueError("lock uses another Python runtime")
        if any(p.get("compatibility_experiment") for p in packages) and not args.allow_misaki_313_experiment:
            raise RuntimeError("lock contains explicit compatibility experiment")
    else:
        packages = resolve(args.allow_misaki_313_experiment)
    records = [{"url": PYTHON_URL, "sha256": PYTHON_SHA256, "filename": PYTHON_URL.rsplit("/", 1)[-1], "name": "python-embeddable"}] + packages
    with ThreadPoolExecutor(max_workers=6) as workers:
        paths = list(workers.map(lambda record: download(record["url"], record["sha256"], args.cache), records))
    if args.output.exists():
        raise RuntimeError("Output already exists; choose a new empty directory to avoid mixing binaries")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".embedded-staging-", dir=args.output.parent))
    try:
        python = staging / "python"
        python.mkdir()
        unpack_archive(paths[0], python)
        site = python / "Lib/site-packages"
        site.mkdir(parents=True)
        for record, path in zip(packages, paths[1:]):
            if path.name.endswith(".tar.gz"):
                path = build_jieba(path, args.cache)
                record["built_wheel"] = {"filename": path.name, "sha256": sha256(path), "build_kind": "host pure-Python packaging; no native extension"}
            if wheel_rank(path.name) is None:
                raise RuntimeError("wheel has incompatible target tags: " + path.name)
            unpack_archive(path, site, wheel=True)
        (python / "python313._pth").write_text("python313.zip\n.\nLib/site-packages\n../app\n../src\nimport site\n", encoding="utf-8")
        copy_sources(staging)
        subprocess.run([sys.executable, str(ROOT / "scripts/collect_dependency_licenses.py"),
                        "--output", str(staging / "licenses/distributions"),
                        "--site-packages", str(site)], check=True)
        binaries = inspect_windows_binaries(python)
        manifest = {"built_at": datetime.now(timezone.utc).isoformat(), "build_host": sys.platform,
                    "target": "Windows 10/11 x64", "assembly_only": True,
                    "native_windows_runtime_verified": False, "wine_runtime_verified": False,
                    "python": {"version": PYTHON_VERSION, "url": PYTHON_URL, "sha256": PYTHON_SHA256,
                               "provenance": "https://www.python.org/downloads/release/python-31317/",
                               "note": "Latest official binary in 3.13 series; 3.13.18 is source-only security release"},
                    "packages": packages, "windows_pe_binaries": binaries,
                    "runtime_prerequisites": [{"name": "Microsoft Visual C++ x64 runtime",
                        "required_dlls": ["MSVCP140.dll", "MSVCP140_1.dll", "VCOMP140.dll"],
                        "bundled": False, "fresh_windows_verified": False,
                        "official_documentation": "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170",
                        "official_download_entry": "https://aka.ms/vc14/vc_redist.x64.exe",
                        "evidence": "Static PE imports of official llama/ONNX Runtime/eSpeak wheels; architecture checks do not establish DLL availability"}],
                    "compatibility_notes": ["Misaki metadata remains original and declares Python<3.13; inclusion is an explicit unverified compatibility experiment", "No model weights downloaded or copied by this builder", "No Linux native modules are permitted in target", "Use Python -I -u -X utf8; _pth includes only bundled app/source/site paths", "App model/voice paths must be explicitly set to resources/backend/models and voices", "VC++ x64 runtime availability on a fresh Windows host must be checked separately; Wine builtins do not establish it"]}
        (staging / "embedded-runtime-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        (staging / "BUILD-STATUS.txt").write_text("Windows x64 files assembled on Linux. Native execution NOT VERIFIED.\nMisaki on Python 3.13 is an upstream-declared-unsupported compatibility experiment.\nMicrosoft VC++ x64 runtime DLLs (MSVCP140, MSVCP140_1, VCOMP140) are prerequisites and are not bundled. Fresh Windows runtime verification is outstanding.\nSee manifest and separate runtime validation evidence.\n")
        staging.rename(args.output)
        print(json.dumps({"output": str(args.output), "packages": len(packages), "windows_pe_binaries": len(binaries), "native_windows_runtime_verified": False}, ensure_ascii=False), flush=True)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    main()
