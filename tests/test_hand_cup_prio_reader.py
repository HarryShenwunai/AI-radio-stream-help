"""Synthetic binary fixtures validate the read-only audit instrument, not art."""
import copy,math,struct,unittest
from hand_cup_authored_identity_check import Reader,decode,grid_summary


def integer(value):return struct.pack('>i',value)
def scalar(value):return struct.pack('>f',value)
def string(value):
    data=value.encode();return integer(len(data))+data
def floats(values):
    fields=[scalar(value)for value in values]
    return integer(len(values))+bytes(field[plane]for plane in range(4)for field in fields)
def ints(values):return integer(len(values))+b''.join(integer(v)for v in values)


def warp_fixture():
    values=[0,0,1,0,0,1,1,1]
    axes=integer(2)+string('ParamCupHold')+floats([0,1])+string('ParamBodyAngleX')+floats([-10,0,10])
    cells=integer(6)+b''.join(ints([hold,body])+floats(values)for hold in range(2)for body in range(3))
    return integer(0x5052494F)+integer(6)+integer(1)+integer(0)+string('TestWarp')+string('Synthetic test only')+b'\0\0'+integer(1)+integer(1)+b'\1\1'+axes+cells+integer(0)+scalar(1)+b''.join(scalar(v)for v in [1,1,1,0,0,0])+b'\1\1\1'+integer(0)


class ReaderTests(unittest.TestCase):
    def test_planar_v6_keeps_raw_float_values(self):
        values=[-.5,0,.25,123.5];reader=Reader(floats(values));self.assertEqual(reader.floats(),values)
        with self.assertRaisesRegex(ValueError,'nonfinite'):Reader(floats([math.nan])).floats()

    def test_complete_constant_hold_zero_table_is_measured_not_assumed(self):
        node=decode(warp_fixture(),1);summary=grid_summary(node)
        self.assertEqual(summary['all_cells'],6);self.assertEqual(summary['hold0_cells'],3)
        self.assertEqual(summary['hold0_unique_bit_forms'],1)
        node['grid']['cells'][1]['form'][0]=.001
        self.assertEqual(grid_summary(node)['hold0_unique_bit_forms'],2)

    def test_missing_or_duplicate_key_cannot_claim_constant_full_table(self):
        node=decode(warp_fixture(),1);node['grid']['cells'].pop()
        with self.assertRaisesRegex(ValueError,'incomplete'):grid_summary(node)
        node=decode(warp_fixture(),1);node['grid']['cells'][1]['coordinate']=node['grid']['cells'][0]['coordinate']
        with self.assertRaisesRegex(ValueError,'duplicate'):grid_summary(node)

    def test_foreign_kind_version_truncation_and_trailing_data_rejected(self):
        data=warp_fixture()
        for value in (b'FAKE'+data[4:],data[:4]+integer(7)+data[8:],data[:-1],data+b'\0'):
            with self.assertRaises(ValueError):decode(value,1)
        with self.assertRaises(ValueError):decode(data,2)


if __name__=='__main__':unittest.main()
