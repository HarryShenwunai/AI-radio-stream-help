"""Synthetic positive/negative instrument controls, never a character pass."""
import math
import unittest
from live2d_cup_geometry import fit_transform,quantiles

REF=[[0,0],[4,0],[4,3],[0,3],[2,1]]
class GeometryTests(unittest.TestCase):
    def test_known_translation_rotation_scale_preserve_similarity(self):
        c,s=math.cos(.37)*1.2,math.sin(.37)*1.2
        target=[[c*x-s*y+1200,s*x+c*y-700]for x,y in REF]
        for kind in ('affine','similarity'):
            fit=fit_transform(REF,target,kind);self.assertLess(fit['max_source_px'],1e-10);self.assertTrue(fit['nondegenerate'])
        self.assertAlmostEqual(fit['similarity_scale'],1.2)
    def test_shear_passes_affine_but_cannot_fake_similarity(self):
        target=[[x+.4*y,y]for x,y in REF]
        self.assertLess(fit_transform(REF,target)['max_source_px'],1e-10)
        self.assertGreater(fit_transform(REF,target,'similarity')['max_source_px'],.1)
    def test_single_vertex_bending_cannot_pass_best_affine(self):
        target=[p[:]for p in REF];target[-1][1]+=1
        self.assertGreater(fit_transform(REF,target)['max_source_px'],.5)
    def test_collapsed_target_reports_scale_degeneracy_even_with_zero_residual(self):
        result=fit_transform(REF,[[7,9]for _ in REF],'similarity')
        self.assertEqual(result['max_source_px'],0);self.assertEqual(result['similarity_scale'],0);self.assertFalse(result['nondegenerate'])
    def test_transparent_unused_vertex_cannot_be_silently_omitted(self):
        target=[p[:]for p in REF];target[-1][0]+=3
        all_fit=fit_transform(REF,target);supported_fit=fit_transform(REF,target,fit_indices=[0,1,2,3])
        self.assertGreater(all_fit['max_source_px'],1);self.assertEqual(max(supported_fit['residual_source_px'][:4]),0);self.assertEqual(supported_fit['residual_source_px'][4],3)
    def test_reflection_cannot_pass_orientation_preserving_similarity(self):
        target=[[-x,y]for x,y in REF]
        self.assertLess(fit_transform(REF,target)['max_source_px'],1e-10);self.assertGreater(fit_transform(REF,target,'similarity')['max_source_px'],1)
    def test_malformed_nonfinite_collinear_and_topology_changes_rejected(self):
        for ref,target in [([[0,0],[1,1],[2,2]],[[0,0],[1,1],[2,2]]),(REF,REF[:-1]),(REF,[[math.nan,0],*REF[1:]]),(REF,[[True,0],*REF[1:]])]:
            with self.assertRaises(ValueError):fit_transform(ref,target)
    def test_quantile_definition_matches_linear_order_statistics(self):
        result=quantiles([0,1,2,3],(50,95));self.assertEqual(result['50'],1.5);self.assertAlmostEqual(result['95'],2.85)
if __name__=='__main__':unittest.main()
