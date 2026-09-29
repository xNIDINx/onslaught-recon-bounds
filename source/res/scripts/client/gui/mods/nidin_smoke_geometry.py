"""Union boundary of disks. No engine dependencies; angles are in X/Z."""
import math

TAU = math.pi * 2
EPS = 1e-7


def boundary_arcs(circles):
    # circle: (x, height, z, radius, team); retain distinct teams even if coincident.
    result = []
    for i, circle in enumerate(circles):
        x, y, z, radius, team = circle
        covered = []
        hidden = False
        for j, other in enumerate(circles):
            if i == j or team != other[4]:
                continue
            dx, dz, r = other[0]-x, other[2]-z, other[3]
            d = math.hypot(dx, dz)
            if d < EPS and abs(radius-r) < EPS:
                if j < i:
                    hidden = True
                    break
                continue
            if d + radius <= r + EPS:
                hidden = True
                break
            if d >= radius+r-EPS or d+r <= radius+EPS:
                continue
            half = math.acos(max(-1.0, min(1.0, (d*d+radius*radius-r*r)/(2*d*radius))))
            a = (math.atan2(dz, dx)-half) % TAU
            b = a + 2*half
            covered.append((a, min(b, TAU)))
            if b > TAU:
                covered.append((0.0, b-TAU))
        if hidden:
            continue
        cursor = 0.0
        for a, b in sorted(covered):
            if a > cursor + EPS:
                result.append((circle, cursor, a))
            cursor = max(cursor, b)
        if cursor < TAU-EPS:
            result.append((circle, cursor, TAU))
    return result


def polylines(circles, step=1.0, max_segments=1024):
    arcs = boundary_arcs(circles)
    # Budget includes mandatory end points of each visible arc. Typical 7-cloud
    # smoke uses about 250 segments. Increase step only for unusually large sets.
    def count(size):
        return sum(max(1, int(math.ceil((b-a)*c[3]/size))) for c,a,b in arcs)
    while count(step) > max_segments and len(arcs) < max_segments:
        step *= 1.25
    result = []
    for c, a, b in arcs:
        n = max(1, int(math.ceil((b-a)*c[3]/step)))
        points = [(c[0]+c[3]*math.cos(a+(b-a)*k/n), c[1],
                   c[2]+c[3]*math.sin(a+(b-a)*k/n)) for k in range(n+1)]
        result.append((c[4], points))
    return result
