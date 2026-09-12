import unittest, sys
sys.path.insert(0, 'B_code/src')
from q2_m6_secondary_refinement import detect_local_minima, window_angles

class TestSecondaryRefinement(unittest.TestCase):
    def test_local_minima_circular(self):
        rs=[]
        for i,v in enumerate([3,2,3,5,4,5]):
            rs.append({'phi_deg':i*2,'boundary_C20':True,'M4':{'JR':v}})
        mm=detect_local_minima(rs, [[0,2,4,6,8,10]])
        self.assertEqual({m['phi_deg'] for m in mm},{2.0,8.0})
    def test_window_dedup_and_wrap(self):
        self.assertEqual(window_angles(0,2,0.5),[0.0,0.5,1.0,1.5,2.0,358.0,358.5,359.0,359.5])
        self.assertEqual(len(window_angles(10,2,0.5)),9)
    def test_seed_order(self):
        rs=[{'phi_deg':0,'boundary_C20':True,'M4':{'JR':2}}, {'phi_deg':2,'boundary_C20':True,'M4':{'JR':1}}, {'phi_deg':4,'boundary_C20':True,'M4':{'JR':2}}]
        self.assertEqual(detect_local_minima(rs)[0]['phi_deg'],2.0)

if __name__=='__main__': unittest.main()
