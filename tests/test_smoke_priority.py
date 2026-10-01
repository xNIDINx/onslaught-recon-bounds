import imp
import math
import os
import random
import unittest

g = imp.load_source('priority_geometry', os.path.join(os.path.dirname(__file__),
    '../source/res/scripts/client/gui/mods/nidin_smoke/geometry.py'))


def disk(x=0, z=0, r=10, team=1, time=100):
    return (x, 0, z, r, team, time)


def owner_at(circles, x, z):
    # Independent point oracle for boundaries sampled on both sides.
    hits = [c for c in circles if math.hypot(x-c[0], z-c[2]) < c[3]]
    if not hits:
        return None
    latest = max(c[5] for c in hits)
    teams = set(c[4] for c in hits if c[5] == latest)
    return next(iter(teams)) if len(teams) == 1 else 0


class PriorityGeometryTests(unittest.TestCase):
    def test_coincident_later_disk_replaces_earlier(self):
        arcs = g.priority_boundary_arcs([disk(), disk(team=2, time=101)])
        self.assertEqual(len(arcs), 1)
        self.assertEqual(arcs[0][0][4], 2)
        self.assertAlmostEqual(arcs[0][2], g.TAU)

    def test_partial_overlap_keeps_crescent_and_one_shared_edge(self):
        arcs = g.priority_boundary_arcs([disk(), disk(x=10, team=2, time=101)])
        lengths = dict((t, sum((b-a)*c[3] for c,a,b in arcs if c[4] == t)) for t in (1,2))
        self.assertAlmostEqual(lengths[1], 40*math.pi/3)
        self.assertAlmostEqual(lengths[2], 20*math.pi)

    def test_new_small_disk_creates_hole_in_older_zone(self):
        arcs = g.priority_boundary_arcs([disk(r=20), disk(r=5, team=2, time=101)])
        self.assertEqual(sorted((c[3], c[4]) for c,a,b in arcs), [(5,2),(20,1)])
        self.assertTrue(all(abs(b-a-g.TAU) < 1e-7 for c,a,b in arcs))

    def test_old_small_disk_is_completely_hidden(self):
        arcs = g.priority_boundary_arcs([disk(r=5), disk(r=20, team=2, time=101)])
        self.assertEqual(len(arcs), 1)
        self.assertEqual(arcs[0][0][4], 2)

    def test_friendly_return_over_enemy_layer(self):
        circles = [disk(r=30), disk(r=20, team=2, time=101), disk(r=10, time=102)]
        arcs = g.priority_boundary_arcs(circles)
        self.assertEqual(sorted((c[3],c[4]) for c,a,b in arcs), [(10,1),(20,2),(30,1)])

    def test_multiple_fragments_and_every_boundary_changes_owner(self):
        circles = [disk(r=20), disk(z=-12,r=16,team=2,time=101), disk(z=12,r=16,team=2,time=101)]
        arcs = g.priority_boundary_arcs(circles)
        old = [(c,a,b) for c,a,b in arcs if c[4] == 1]
        self.assertGreaterEqual(len(old), 2)
        self.assertEqual(owner_at(circles,-19,0),1)
        self.assertEqual(owner_at(circles,19,0),1)
        self.assertEqual(owner_at(circles,0,0),2)
        self.assert_edges(circles,arcs)

    def test_equal_timestamp_does_not_use_input_order(self):
        circles = [disk(), disk(team=2)]
        self.assertEqual(g.priority_boundary_arcs(circles), g.priority_boundary_arcs(circles[::-1]))
        self.assertEqual(g.priority_boundary_arcs(circles)[0][0][4],0)

    def test_unknown_latest_stays_neutral(self):
        self.assertEqual(g.priority_boundary_arcs([disk(),disk(team=0,time=101)])[0][0][4],0)

    def test_same_team_has_no_internal_edges(self):
        circles = [disk(), disk(x=10,time=102)]
        arcs = g.priority_boundary_arcs(circles)
        self.assertAlmostEqual(sum((b-a)*c[3] for c,a,b in arcs),80*math.pi/3)

    def test_tangent_and_disjoint_remain_separate(self):
        for distance in (20,25):
            self.assertEqual(len(g.priority_boundary_arcs([disk(),disk(x=distance,team=2,time=101)])),2)

    def assert_edges(self,circles,arcs):
        for c,a,b in arcs:
            for fraction in (0.17,0.5,0.83):
                angle=a+(b-a)*fraction
                x,z=c[0]+c[3]*math.cos(angle),c[2]+c[3]*math.sin(angle)
                dx,dz=1e-5*math.cos(angle),1e-5*math.sin(angle)
                inside=owner_at(circles,x-dx,z-dz)
                outside=owner_at(circles,x+dx,z+dz)
                self.assertNotEqual(inside,outside)
                self.assertEqual(inside,c[4])

    def test_random_arrangements_match_point_oracle_and_permutations(self):
        rng=random.Random(31415)
        for unused in range(30):
            circles=[disk(rng.uniform(-20,20),rng.uniform(-20,20),rng.uniform(8,20),
                          rng.choice((1,2)),rng.randrange(4)) for j in range(10)]
            arcs=g.priority_boundary_arcs(circles)
            self.assert_edges(circles,arcs)
            rng.shuffle(circles)
            self.assertEqual(arcs,g.priority_boundary_arcs(circles))

    def test_polyline_steps_and_shared_boundary_are_identical_between_layers(self):
        arcs=g.priority_boundary_arcs([disk(r=37.5),disk(x=35,r=37.5,team=2,time=101)])
        mini=g.polylines_from_arcs(arcs,1.0)
        terrain=g.polylines_from_arcs(arcs,3.0)
        self.assertEqual([(t,p[0],p[-1]) for t,p in mini],[(t,p[0],p[-1]) for t,p in terrain])
        self.assertLess(sum(len(p)-1 for t,p in terrain),sum(len(p)-1 for t,p in mini))

    def test_no_missing_edges_against_independent_angular_samples(self):
        rng=random.Random(2026)
        for unused in range(10):
            circles=[disk(rng.uniform(-20,20),rng.uniform(-20,20),rng.uniform(8,20),
                          rng.choice((1,2)),rng.randrange(4)) for j in range(8)]
            arcs=g.priority_boundary_arcs(circles)
            for c in circles:
                for k in range(120):
                    angle=(k+0.37)*g.TAU/120
                    x,z=c[0]+c[3]*math.cos(angle),c[2]+c[3]*math.sin(angle)
                    dx,dz=1e-6*math.cos(angle),1e-6*math.sin(angle)
                    expected=owner_at(circles,x-dx,z-dz)!=owner_at(circles,x+dx,z+dz)
                    actual=any(draw[:4]==c[:4] and a<angle<b for draw,a,b in arcs)
                    self.assertEqual(actual,expected)


if __name__ == '__main__':
    unittest.main()
