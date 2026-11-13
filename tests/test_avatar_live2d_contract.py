"""Geometry gates for genuinely observed Core grip/finger landmarks."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "avatar_contract", Path(__file__).resolve().parents[1] / "scripts/avatar_live2d_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ActualCoreLandmarkTests(unittest.TestCase):
    def test_barycentric_anchor_reconstructs_and_follows_affine_pose(self):
        rest = [(0, 0), (100, 0), (0, 100)]
        anchor = MODULE.bind_point(rest, [0, 1, 2], [25, 50])
        self.assertEqual(anchor["weights"], [.25, .25, .5])
        # One observed triangle moves; fixed barycentric weights must follow it.
        posed = [(7, 12), (207, 12), (7, 312)]
        actual = [sum(posed[i][axis] * w for i, w in zip(anchor["vertex_indices"], anchor["weights"]))
                  for axis in (0, 1)]
        self.assertEqual(actual, [57, 162])

    def test_outside_mesh_never_falls_back_to_closest_vertex(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            MODULE.bind_point([(0, 0), (1, 0), (0, 1)], [0, 1, 2], [1, 1])

    def test_degenerate_triangle_does_not_fake_an_anchor(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            MODULE.bind_point([(0, 0), (1, 0), (2, 0)], [0, 1, 2], [1, 0])

    def test_core_y_is_converted_to_canvas_downwards(self):
        points = MODULE.source_points({"vertexPositions": [0, 0, 1, 0, 0, 1]},
                                      {"originX": 768, "originY": 1024, "ppu": 1536})
        self.assertEqual(points, [(768, 1024), (2304, 1024), (768, -512)])

    def test_invalid_indices_and_nonfinite_values_fail(self):
        for bad in [True, -1, 3, .5]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                MODULE.bind_point([(0, 0), (1, 0), (0, 1)], [0, 1, bad], [.1, .1])
        with self.assertRaises(ValueError):
            MODULE.bind_point([(0, 0), (1, 0), (0, 1)], [0, 1, 2], [float("nan"), 0])

    def test_independent_snapshot_requires_stable_source_and_actual_defaults(self):
        snapshot = {"status": "measured_private_original_model_snapshot", "sources_unchanged": False}
        with self.assertRaisesRegex(ValueError, "sources changed"):
            MODULE.build(snapshot, {})
        snapshot.update(sources_unchanged=True, measurement={"consistency": 1,
                        "parameters": [{"value": .5, "default": 0}]})
        with self.assertRaisesRegex(ValueError, "actual parameter defaults"):
            MODULE.build(snapshot, {})

    def test_duplicate_drawable_ids_cannot_misbind_a_landmark(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.build({"format": "actual-live2d-core-rest-v1", "canvasInfo": {},
                          "drawables": [{"id": "cup"}, {"id": "cup"}]}, {})


if __name__ == "__main__":
    unittest.main()
