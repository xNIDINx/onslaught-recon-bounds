import imp, os, math, unittest
g = imp.load_source('smoke_geometry', os.path.join(os.path.dirname(__file__), '../source/res/scripts/client/gui/mods/nidin_smoke_geometry.py'))

class GeometryTests(unittest.TestCase):
    def test_single_circle(self):
        arcs=g.boundary_arcs([(0,0,0,10,1)])
        self.assertEqual(len(arcs),1)
        self.assertAlmostEqual(arcs[0][2],2*math.pi)

    def test_two_overlapping_circles_exact_intersection_angles(self):
        arcs=g.boundary_arcs([(0,0,0,10,1),(10,0,0,10,1)])
        self.assertAlmostEqual(sum((b-a)*c[3] for c,a,b in arcs),80*math.pi/3)
        for c,a,b in arcs:
            angle=(a+b)/2
            px,pz=c[0]+10*math.cos(angle),c[2]+10*math.sin(angle)
            other=10 if c[0]==0 else 0
            self.assertGreaterEqual(math.hypot(px-other,pz),10-1e-7)

    def test_containment_and_duplicates(self):
        arcs=g.boundary_arcs([(0,0,0,10,1),(1,0,0,2,1),(0,0,0,10,1)])
        self.assertEqual(len(arcs),1)

    def test_enemy_is_not_subtracted(self):
        self.assertEqual(len(g.boundary_arcs([(0,0,0,10,1),(0,0,0,10,2)])),2)

    def test_disjoint_and_tangent(self):
        for distance in (20,25):
            self.assertEqual(len(g.boundary_arcs([(0,0,0,10,1),(distance,0,0,10,1)])),2)

    def test_collective_cover_hides_center_circle(self):
        circles=[(0,0,0,10,1)]+[(5*math.cos(a),0,5*math.sin(a),10,1) for a in (0,2*math.pi/3,4*math.pi/3)]
        self.assertFalse(any(c is circles[0] for c,a,b in g.boundary_arcs(circles)))

    def test_inner_hole_keeps_its_boundary(self):
        circles=[(10*math.cos(a),0,10*math.sin(a),9,1) for a in (0,2*math.pi/3,4*math.pi/3)]
        arcs=g.boundary_arcs(circles)
        self.assertTrue(any(math.hypot(c[0]+9*math.cos((a+b)/2),c[2]+9*math.sin((a+b)/2))<3 for c,a,b in arcs))

    def test_polyline_endpoints_and_budget(self):
        lines=g.polylines([(0,0,0,37.5,1)])
        self.assertAlmostEqual(lines[0][1][0][0],lines[0][1][-1][0])
        self.assertEqual(sum(len(p)-1 for t,p in lines),236)
        for team, points in lines:
            for p,q in zip(points,points[1:]):
                self.assertLessEqual(math.hypot(p[0]-q[0],p[2]-q[2]),1.0)
        lines=g.polylines([(100*i,0,0,37.5,1) for i in range(64)])
        self.assertLessEqual(sum(len(p)-1 for t,p in lines),1024)

if __name__=='__main__':unittest.main()
