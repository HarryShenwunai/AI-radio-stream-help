"""Source gates reject metadata-only animation and false completion claims."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("avatar_pipeline", ROOT / "scripts/avatar_pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
CONTRACT = json.loads(pipeline.CONTRACT.read_text())


def healthy_observation():
    names = CONTRACT["required_humanoid"]
    ancestors = {}
    for name in names:
        current = name
        parents = []
        while current in pipeline.PARENTS:
            current = pipeline.PARENTS[current]
            parents.append(current)
        ancestors[name] = parents
    return {
        "armature_count": 1, "humanoid": {name: name for name in names},
        "bone_ancestors": ancestors, "look_at_type": "bone",
        "meshes": [{"name": "Face", "vertices": 8, "rig_bound": True,
                    "unweighted_vertices": 0, "unnormalized_vertices": 0,
                    "max_influences": 4, "uv_layers": 1, "materials": 1}],
        "instance_triangles": 12, "images": [], "external_libraries": [],
        "expressions": {name: [{"mesh": "Face", "key": name, "weight": 1, "max_delta": 0.01}]
                        for name in CONTRACT["required_expressions"]},
    }


INVALID_CASES = [
    (lambda r: r["expressions"]["aa"][0].update(max_delta=0), "missing_nonzero_expression_bind:aa"),
    (lambda r: r["expressions"]["blink"][0].update(mesh="HiddenFace"), "missing_nonzero_expression_bind:blink"),
    (lambda r: r["bone_ancestors"].update(leftEye=[]), "invalid_hierarchy:leftEye:head"),
    (lambda r: r["meshes"][0].update(unweighted_vertices=1), "unweighted_vertices:Face"),
    (lambda r: r["meshes"][0].update(max_influences=5), "too_many_influences:Face"),
    (lambda r: r["meshes"][0].update(rig_bound=False), "mesh_not_bound_to_humanoid:Face"),
    (lambda r: r.update(instance_triangles=150001), "triangle_review_budget_exceeded"),
    (lambda r: r.update(images=[{"name": "A", "width": 4096, "height": 4096, "packed": True},
                              {"name": "B", "width": 4096, "height": 4096, "packed": True}]),
     "texture_pixel_budget_exceeded"),
]


class AvatarSourceGates(unittest.TestCase):
    def test_structural_pass_cannot_claim_character_or_visual_complete(self):
        verdict = pipeline.evaluate(healthy_observation(), CONTRACT)
        self.assertEqual(verdict["structural_status"], "PASS")
        self.assertFalse(verdict["final_character_complete"])
        self.assertEqual(verdict["visual_reference_acceptance"], "NOT_RUN")
        self.assertEqual(verdict["runtime_performance_acceptance"], "NOT_RUN")

    def test_invalid_source_gates(self):
        for mutation, issue in INVALID_CASES:
            with self.subTest(issue=issue):
                report = healthy_observation()
                mutation(report)
                verdict = pipeline.evaluate(report, CONTRACT)
                self.assertEqual(verdict["structural_status"], "FAIL")
                self.assertIn(issue, verdict["issues"])

    def test_absent_reference_blocks_before_blender_can_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = subprocess.run([sys.executable, str(ROOT / "scripts/avatar_pipeline.py"), "audit",
                                     "--blender", "/must-not-be-executed", "--output", str(output)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads((output / "audit.json").read_text())["status"], "BLOCKED_REFERENCE_MISSING")
            self.assertFalse((output / "candidate.vrm").exists())

    def test_modified_addon_is_rejected_before_blender_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            module = output / pipeline.ADDON_MODULE
            module.mkdir()
            source = module / "__init__.py"
            source.write_text("original")
            receipt = {"version": pipeline.ADDON_VERSION, "archive_sha256": pipeline.ADDON_SHA256,
                       "files": {f"{pipeline.ADDON_MODULE}/__init__.py": pipeline.file_sha(source)}}
            (output / ".avatar-addon-lock.json").write_text(json.dumps(receipt))
            pipeline.verify_addon(output)
            source.write_text("changed")
            with self.assertRaisesRegex(ValueError, "was modified"):
                pipeline.verify_addon(output)

    def test_no_art_acceptance_was_invented_in_contract(self):
        self.assertFalse(CONTRACT["final_character_complete"])
        self.assertEqual(set(CONTRACT["acceptance"].values()), {"NOT_RUN"})


if __name__ == "__main__":
    unittest.main()
