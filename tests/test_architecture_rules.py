"""Mutation fixtures prove the executable architecture checks reject regressions.

Fixtures only mutate copies in memory/temporary directories, never app sources.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "companion_architecture", ROOT / "scripts/check_architecture.py"
)
architecture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = architecture
SPEC.loader.exec_module(architecture)


class ArchitectureFixture(unittest.TestCase):
    def setUp(self):
        self.sources = {
            path: (ROOT / path).read_text(encoding="utf-8")
            for path in (
                *architecture.PUBLIC,
                *architecture.ASSETS,
                *architecture.ADVICE,
                "app/server.py",
            )
        }
        self.package = json.loads(
            (ROOT / "frontend/package.json").read_text(encoding="utf-8")
        )
        self.lock = json.loads(
            (ROOT / "frontend/package-lock.json").read_text(encoding="utf-8")
        )
        self.static = [
            str(path.relative_to(ROOT))
            for path in (ROOT / "app/static").rglob("*")
            if path.is_file()
        ]

    def violations(self):
        return architecture.check_sources(
            self.sources, self.static, self.package, self.lock
        )

    def reject(self, rule):
        self.assertIn(rule, {failure.rule for failure in self.violations()})

    def server(self):
        return ast.parse(self.sources["app/server.py"])

    def save(self, tree):
        self.sources["app/server.py"] = ast.unparse(ast.fix_missing_locations(tree))

    def plugin_branch(self, tree):
        return next(
            n
            for n in ast.walk(tree)
            if architecture.route_branch(n, "/api/connectors/wechat/inbound")
        )


class ArchitectureMutationTests(ArchitectureFixture):
    def test_current_source_baseline_passes(self):
        self.assertEqual([], self.violations())

    def test_public_ingress_storage_import_fails(self):
        self.sources[architecture.PUBLIC[0]] += "\nimport sqlite3 as data_store\n"
        self.reject("A01")

    def test_public_private_prompt_alias_fails(self):
        tree = self.server()
        function = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "public_model_settings"
        )
        function.body = ast.parse(
            "private_config = settings\nreturn private_config()"
        ).body
        self.save(tree)
        self.reject("A02")

    def test_role_package_script_execution_fails(self):
        self.sources[architecture.ASSETS[0]] += (
            "\ndef bad_asset(value):\n    return eval(value)\n"
        )
        self.reject("A03")

    def test_layered_character_parser_is_covered_by_execution_gate(self):
        path = "src/companion_runtime/layered_2d_assets.py"
        self.assertIn(path, architecture.ASSETS)
        self.sources[path] += "\nimport subprocess as layer_executor\n"
        self.reject("A03")

    def test_assistance_cannot_acquire_external_execution_transport(self):
        self.sources[architecture.ADVICE[0]] += "\nimport subprocess as tools\n"
        self.reject("A07")

    def test_preference_learning_cannot_own_network_or_tools(self):
        original = self.sources[architecture.ADVICE[1]]
        for injected in (
            "import urllib.request as service",
            "import subprocess as tool",
        ):
            with self.subTest(injected=injected):
                self.sources[architecture.ADVICE[1]] = original + "\n" + injected + "\n"
                self.reject("A07")

    def test_sdk_bytes_in_default_static_fails(self):
        self.static.append("app/static/vendor/live2dcubismcore.min.js")
        self.reject("A04")

    def test_sdk_dependency_in_default_graph_fails(self):
        self.package.setdefault("dependencies", {})["pixi-live2d-display"] = "fixture"
        self.reject("A04")

    def test_plugin_route_capability_expansion_fails(self):
        tree = self.server()
        branch = self.plugin_branch(tree)
        container = next(
            n
            for n in ast.walk(branch.test)
            if isinstance(n, (ast.Set, ast.Tuple, ast.List))
        )
        container.elts.append(ast.Constant(value="/api/settings"))
        self.save(tree)
        self.reject("A05")

    def test_plugin_owner_operation_fails(self):
        tree = self.server()
        self.plugin_branch(tree).body.insert(0, ast.parse("approve({})").body[0])
        self.save(tree)
        self.reject("A05")

    def test_plugin_cannot_reach_new_host_capture_advice_or_learning(self):
        original = self.sources["app/server.py"]
        for helper in (
            "perception_request",
            "assistance_request",
            "preference_request",
            "update_devices",
            "host_services",
            "preference_store",
            "assistance_store",
        ):
            with self.subTest(helper=helper):
                self.sources["app/server.py"] = original
                tree = self.server()
                self.plugin_branch(tree).body.insert(
                    0, ast.parse(helper + "()").body[0]
                )
                self.save(tree)
                self.reject("A05")

    def test_plugin_missing_authentication_fails(self):
        class RemoveAuthentication(ast.NodeTransformer):
            def visit_Expr(self, node):
                if (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "authenticate"
                ):
                    return ast.copy_location(ast.Pass(), node)
                return self.generic_visit(node)

        tree = self.server()
        branch = self.plugin_branch(tree)
        branch.body = [
            RemoveAuthentication().visit(statement) for statement in branch.body
        ]
        self.save(tree)
        self.reject("A05")

    def test_binary_response_double_serialization_fails(self):
        tree = self.server()
        handler = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Handler"
        )
        reply = next(
            n
            for n in handler.body
            if isinstance(n, ast.FunctionDef) and n.name == "reply"
        )
        reply.body = ast.parse(
            "body = json.dumps(data).encode('utf-8')\nself.wfile.write(body)"
        ).body
        self.save(tree)
        self.reject("A06")

    def test_real_cli_rejects_fixture_with_exit_one(self):
        self.sources[architecture.PUBLIC[1]] += "\nimport sqlite3\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, source in self.sources.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")
            (root / "frontend").mkdir()
            for name, value in (
                ("package.json", self.package),
                ("package-lock.json", self.lock),
            ):
                (root / "frontend" / name).write_text(
                    json.dumps(value), encoding="utf-8"
                )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/check_architecture.py"),
                    "--root",
                    str(root),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(1, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["passed"])
            self.assertIn("A01", {entry["rule"] for entry in report["violations"]})


class MissingConnectionContractTests(ArchitectureFixture):
    def test_audit27_missing_connection_fields_is_rejected(self):
        tree = self.server()
        tree.body = [
            n
            for n in tree.body
            if not isinstance(n, ast.Assign)
            or not any(
                isinstance(t, ast.Name) and t.id == "CONNECTION_FIELDS"
                for t in n.targets
            )
        ]
        self.save(tree)
        self.reject("A02")


class QualifiedExecutionContractTests(ArchitectureFixture):
    def test_audit28_qualified_eval_cannot_bypass_boundary(self):
        self.sources[architecture.ASSETS[0]] += (
            "\nimport builtins\ndef unsafe(value):\n return builtins.eval(value)\n"
        )
        self.reject("A03")
        self.sources[architecture.ADVICE[0]] += (
            "\nimport builtins\ndef unsafe(value):\n return builtins.exec(value)\n"
        )
        self.reject("A07")


class ProposalFileContentContractTests(ArchitectureFixture):
    def test_audit29_proposals_cannot_read_arbitrary_files(self):
        self.sources[architecture.ADVICE[0]] += (
            "\ndef unsafe(path):\n return Path(path).read_text()\n"
        )
        self.reject("A07")


class VendorAliasContractTests(ArchitectureFixture):
    def test_audit30_npm_alias_cannot_bypass_optional_sdk_boundary(self):
        self.package.setdefault("dependencies", {})["innocent-name"] = (
            "npm:@live2d/cubism-core@1.0.0"
        )
        self.reject("A04")


if __name__ == "__main__":
    unittest.main()
