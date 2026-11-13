"""Executable local architecture contracts. This is not a complete taint proof.

AST checks enforce known module/import/call boundaries. JSON checks keep optional
Live2D vendor dependencies out of the default frontend. Real HTTP tests separately
verify authentication, cancellation and data flow at runtime.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ("src/companion_runtime/live.py", "src/companion_runtime/connectors/bilibili.py")
ASSETS = tuple("src/companion_runtime/" + name + ".py" for name in ("assets", "vrm_assets", "live2d_assets", "layered_2d_assets"))
ADVICE = ("src/companion_runtime/assistance.py", "src/companion_runtime/preference_learning.py")
PRIVATE_MODULES = frozenset({"app", "server", "sqlite3", "characters", "conversation", "runtime_settings", "integration_service", "playback"})
PRIVATE_CALLS = frozenset({"settings", "db", "build_prompt", "select_memories", "chat", "profile_context", "state", "_state"})
EXECUTION_CALLS = frozenset({"eval", "exec", "compile", "__import__"})
OWNER_CALLS = frozenset({"approve", "set_settings", "connector_request", "configure_wechat", "configure_bili", "character_request",
                         "perception_request", "assistance_request", "preference_request", "update_devices",
                         "host_services", "preference_store", "assistance_store"})
PLUGIN_ROUTES = frozenset("/api/connectors/wechat/" + name for name in ("inbound", "claim", "ack"))
VENDOR_PACKAGES = frozenset({"pixi-live2d-display", "@jannchie/pixi-live2d-display", "@live2d/cubism-core", "@live2d/cubism-framework"})


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    detail: str


def names(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.Attribute):
        yield node.attr
        yield from names(node.value)


def imports(tree: ast.AST) -> Iterable[tuple[ast.AST, str, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name, alias.asname or alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            yield node, module, module
            for alias in node.names:
                yield node, module + "." + alias.name, alias.asname or alias.name


def aliases(tree: ast.AST) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for _, module, bound in imports(tree):
        result.setdefault(bound, set()).update(module.split("."))
    # Resolve simple aliases conservatively, including aliases declared later.
    assignments = [n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))]
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            value = node.value
            if not isinstance(value, (ast.Name, ast.Attribute)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            refs = set(names(value))
            for ref in list(refs):
                refs.update(result.get(ref, set()))
            for target in targets:
                if not isinstance(target, ast.Name):continue
                old = result.setdefault(target.id, set())
                before = len(old)
                old.update(refs)
                changed |= len(old) != before
        if not changed:break
    return result


def call_names(call: ast.Call, bindings: dict[str, set[str]]) -> set[str]:
    result = set(names(call.func))
    for value in list(result):result.update(bindings.get(value, set()))
    return result


def route_branch(node: ast.AST, value: str) -> bool:
    return isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and any(
        isinstance(child, ast.Constant) and child.value == value for child in ast.walk(node.test))


def _authenticated_before(call: ast.Call, boundary: ast.If, parents: dict[ast.AST, ast.AST]) -> bool:
    """A standalone authentication call must dominate the action in its block.

    Conditional/exception-handler calls do not establish authentication outside
    their block. This deliberately accepts an explicit linear guard style only.
    """
    current: ast.AST = call
    while current is not boundary:
        parent = parents.get(current)
        if parent is None:return False
        for _, value in ast.iter_fields(parent):
            if isinstance(value, list) and current in value:
                for prior in value[:value.index(current)]:
                    if (isinstance(prior, ast.Expr) and isinstance(prior.value, ast.Call)
                            and isinstance(prior.value.func, ast.Attribute)
                            and prior.value.func.attr == "authenticate"):
                        return True
        current = parent
    return False


def check_sources(sources: dict[str, str], static_names: Iterable[str] = (), frontend_packages: dict | None = None,
                  frontend_lock: dict | None = None) -> list[Violation]:
    failures: list[Violation] = []
    trees: dict[str, ast.Module] = {}
    for path, source in sources.items():
        try:trees[path] = ast.parse(source, filename=path)
        except SyntaxError as error:
            failures.append(Violation("A00", path, error.lineno or 0, "Python source cannot be parsed"))
    for path in (*PUBLIC, *ASSETS, *ADVICE, "app/server.py"):
        if path not in trees:
            failures.append(Violation("A00", path, 0, "Required architecture boundary is missing"))
    for path in PUBLIC:
        tree = trees.get(path)
        if tree is None:continue
        for node, module, _ in imports(tree):
            if set(module.split(".")) & PRIVATE_MODULES:
                failures.append(Violation("A01", path, node.lineno, "Public ingress imports private storage/application code"))
    for path in ASSETS:
        tree = trees.get(path)
        if tree is None:continue
        bindings = aliases(tree)
        forbidden_imports = {"subprocess", "ctypes", "importlib", "runpy", "requests", "aiohttp", "httpx", "urllib", "socket"}
        for node, module, _ in imports(tree):
            if set(module.split(".")) & forbidden_imports:
                failures.append(Violation("A03", path, node.lineno, "Role asset parser imports execution/network machinery"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):continue
            refs = call_names(node, bindings)
            bare_execution = isinstance(node.func, ast.Name) and bool(refs & EXECUTION_CALLS)
            if bare_execution or refs & {"system", "popen", "exec_module", "import_module", "run_path", "urlopen"}:
                failures.append(Violation("A03", path, node.lineno, "Role asset parser may execute code or contact a service"))
    for path in ADVICE:
        tree = trees.get(path)
        if tree is None:continue
        bindings = aliases(tree)
        forbidden = {"app", "server", "conversation", "characters", "integration_service", "subprocess", "ctypes", "importlib", "runpy", "requests", "aiohttp", "httpx", "urllib", "socket"}
        for node, module, _ in imports(tree):
            if set(module.split(".")) & forbidden:
                failures.append(Violation("A07", path, node.lineno, "Proposal modules may not import application helpers, execute tools or own a network transport"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):continue
            refs = call_names(node, bindings)
            if ((isinstance(node.func, ast.Name) and bool(refs & (EXECUTION_CALLS | {"open"})))
                    or refs & {"system", "popen", "exec_module", "import_module", "run_path", "urlopen"}):
                failures.append(Violation("A07", path, node.lineno, "Assistance may only parse supplied data and use its scoped ledger; executable tools are forbidden"))
    server = trees.get("app/server.py")
    if server is not None:
        bindings = aliases(server)
        functions = {n.name:n for n in server.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for required in ("public_model_settings", "load_model", "connector_request"):
            if required not in functions:
                failures.append(Violation("A02", "app/server.py", 0, "Required shared/public function is missing: " + required))
        regions: list[ast.AST] = [functions[k] for k in ("public_model_settings", "load_model") if k in functions]
        connector = functions.get("connector_request")
        branches = [node for node in ast.walk(connector) if route_branch(node, "bili/reply")] if connector else []
        if not branches:
            failures.append(Violation("A02", "app/server.py", 0, "Explicit public reply branch is missing"))
        for branch in branches:regions.extend(branch.body)
        for region in regions:
            for node in ast.walk(region):
                if isinstance(node, ast.Call) and call_names(node, bindings) & PRIVATE_CALLS:
                    failures.append(Violation("A02", "app/server.py", node.lineno, "Shared/public model path calls private conversation/storage code"))
        field_declarations = [node for node in server.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CONNECTION_FIELDS" for t in node.targets)]
        if len(field_declarations) != 1:
            failures.append(Violation("A02", "app/server.py", 0, "Exactly one connection field allowlist is required"))
        for node in field_declarations:
            if isinstance(node, ast.Assign):
                try:fields = set(ast.literal_eval(node.value))
                except (ValueError, TypeError):fields = set()
                if fields != {"engine", "api_base", "api_model"}:
                    failures.append(Violation("A02", "app/server.py", node.lineno, "Shared connection fields exceed the explicit transport allowlist"))
        parents = {child:parent for parent in ast.walk(server) for child in ast.iter_child_nodes(parent)}
        plugin_regions = []
        for node in ast.walk(server):
            if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):continue
            constants = {v.value for v in ast.walk(node.test) if isinstance(v, ast.Constant) and isinstance(v.value, str)}
            if not constants & PLUGIN_ROUTES:continue
            plugin_regions.append(node)
            routes = {v for v in constants if v.startswith("/api/")}
            if routes != PLUGIN_ROUTES:
                failures.append(Violation("A05", "app/server.py", node.lineno, "Plugin token route allowlist changed"))
            for child in [c for statement in node.body for c in ast.walk(statement) if isinstance(c, ast.Call)]:
                refs = call_names(child, bindings)
                if refs & OWNER_CALLS:
                    failures.append(Violation("A05", "app/server.py", child.lineno, "Plugin transport branch reaches an owner operation"))
                if refs & {"ingest", "claim", "acknowledge"} and not _authenticated_before(child, node, parents):
                    failures.append(Violation("A05", "app/server.py", child.lineno, "Transport action is not dominated by authentication"))
        if len(plugin_regions) != 1:
            failures.append(Violation("A05", "app/server.py", 0, "Exactly one explicit plugin transport branch is required"))
        handlers = [n for n in server.body if isinstance(n, ast.ClassDef) and n.name == "Handler"]
        replies = [n for cls in handlers for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "reply"]
        if len(replies) != 1:
            failures.append(Violation("A06", "app/server.py", 0, "Exactly one typed serialization adapter is required"))
        else:
            calls = [n for n in ast.walk(replies[0]) if isinstance(n, ast.Call)]
            serializers = [n for n in calls if "encode_http_body" in call_names(n, bindings)]
            if len(serializers) != 1:
                failures.append(Violation("A06", "app/server.py", replies[0].lineno, "Handler.reply must delegate once to encode_http_body"))
            for call in calls:
                if "dumps" in call_names(call, bindings):
                    failures.append(Violation("A06", "app/server.py", call.lineno, "Handler.reply must not JSON-serialize opaque asset bytes"))
    forbidden_files = {"live2dcubismcore.min.js", "live2dcubismcore.js", "live2d-runtime.js"}
    for path in static_names:
        if Path(path).name.lower() in forbidden_files or Path(path).suffix.lower() in {".moc3", ".vrm"}:
            failures.append(Violation("A04", path, 0, "Optional SDK/model bytes must not ship in default static files"))
    package = frontend_packages or {}
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name in package.get(section, {}):
            if name in VENDOR_PACKAGES:
                failures.append(Violation("A04", "frontend/package.json", 0, "Optional Live2D vendor dependency entered default install graph"))
    for path in (frontend_lock or {}).get("packages", {}):
        if any(path.endswith("node_modules/" + name) for name in VENDOR_PACKAGES):
            failures.append(Violation("A04", "frontend/package-lock.json", 0, "Optional Live2D vendor bytes entered default lock graph"))
    return failures


def check_project(root: Path) -> list[Violation]:
    sources = {str(path.relative_to(root)).replace('\\','/'):path.read_text(encoding="utf-8")
               for path in [*(root/path for path in (*PUBLIC, *ASSETS, *ADVICE)), root/"app/server.py"] if path.is_file()}
    packages = json.loads((root/"frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root/"frontend/package-lock.json").read_text(encoding="utf-8"))
    static = [str(path.relative_to(root)).replace('\\','/') for path in (root/"app/static").rglob('*') if path.is_file()]
    return check_sources(sources, static, packages, lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:violations = check_project(args.root.resolve())
    except (OSError, ValueError) as error:
        print(json.dumps({"passed":False,"error":type(error).__name__}))
        return 1
    print(json.dumps({"passed":not violations,"rules":["A01","A02","A03","A04","A05","A06","A07"],
                      "violations":[asdict(v) for v in violations],
                      "limits":"AST/import/call contracts and default dependency graph; not whole-program taint or SDK legal certification"}, ensure_ascii=False, indent=2))
    return 1 if violations else 0


if __name__ == "__main__":raise SystemExit(main())
