"""Independent interpolation instrument tests; no claim about model geometry."""
import itertools,unittest
from hand_cup_palm_multilinear_probe import interpolate


class InterpolationTests(unittest.TestCase):
    def test_exact_key_does_not_blend_neighbours(self):
        samples={(0,):[[1,2],[3,4]],(1,):[[100,200],[300,400]]}
        self.assertEqual(interpolate(samples,{'x':[0,1]},{'x':0}),[[1,2],[3,4]])

    def test_cross_terms_are_multilinear_not_naive_axis_addition(self):
        levels={'x':[0,2],'y':[-1,1]}
        samples={(x,y):[[x*y+3*x,4*y],[x-y,x*y]]for x,y in itertools.product(*levels.values())}
        self.assertEqual(interpolate(samples,levels,{'x':.5,'y':.25}),[[1.625,1],[.25,.125]])

    def test_missing_corner_and_extrapolation_fail(self):
        with self.assertRaisesRegex(ValueError,'missing actual'):
            interpolate({(0,):[[0,0],[0,0]]},{'x':[0,1]},{'x':.5})
        with self.assertRaisesRegex(ValueError,'extrapolation'):
            interpolate({},{'x':[0,1]},{'x':2})


if __name__=='__main__':unittest.main()
