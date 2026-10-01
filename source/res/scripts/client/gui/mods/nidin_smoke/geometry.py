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
    return polylines_from_arcs(boundary_arcs(circles), step, max_segments)


def priority_boundary_arcs(circles):
    """Experimental latest-start-wins regions, not a server effect query.

    Circle: (x, height, z, radius, team, server_start_time).
    Draw each interface once, in the inside/newer region's colour. Equal
    timestamps with different teams, or an unknown winning team, use team 0.
    Arrival order and smoke IDs never resolve a tie.
    """
    groups = {}
    for c in circles:
        groups.setdefault((c[0], c[2], c[3]), []).append(c)
    # Coincident boundaries are one curve, even across teams. Deterministic
    # order also makes replay snapshots independent of dictionary iteration.
    disks = []
    for key in sorted(groups):
        group = groups[key]
        circle = sorted(group, key=lambda c: (-c[5], c[1], c[4]))[0]
        teams = set(c[4] for c in group if c[5] == circle[5])
        team = next(iter(teams)) if len(teams) == 1 else 0
        disks.append(circle[:4]+(team, circle[5]))
    ranked = sorted(enumerate(disks), key=lambda item: -item[1][5])

    result = []
    for i, circle in enumerate(disks):
        x, y, z, radius = circle[:4]
        cuts = [0.0, TAU]
        possible = []
        for j, other in ranked:
            if i == j:
                continue
            dx, dz, r = other[0]-x, other[2]-z, other[3]
            d = math.hypot(dx, dz)
            if d >= radius+r-EPS:
                continue
            possible.append(other)
            if d < EPS or d+min(radius, r) <= max(radius, r)+EPS:
                continue
            half = math.acos(max(-1.0, min(1.0, (d*d+radius*radius-r*r)/(2*d*radius))))
            angle = math.atan2(dz, dx)
            cuts.extend(((angle-half) % TAU, (angle+half) % TAU))
        cuts = sorted(set(cuts))
        previous = None
        for a, b in zip(cuts, cuts[1:]):
            if b-a <= EPS:
                continue
            angle = (a+b)*0.5
            px, pz = x+radius*math.cos(angle), z+radius*math.sin(angle)
            outer_team = None
            outer_time = None
            hidden = False
            for c in possible:
                # Only the newest covering timestamp matters. In dense sets,
                # terminate as soon as a newer disk covers both sides of this
                # arc. No need to classify every older cloud at every interval.
                if outer_time is not None and c[5] < outer_time:
                    break
                if (px-c[0])**2+(pz-c[2])**2 < c[3]**2:
                    if c[5] > circle[5]:
                        hidden = True
                        break
                    if outer_time is None:
                        outer_time, outer_team = c[5], c[4]
                    elif outer_team != c[4]:
                        outer_team = 0
            if hidden:
                previous = None
                continue
            inner_team = circle[4]
            if outer_time == circle[5] and outer_team != inner_team:
                inner_team = 0
            if inner_team == outer_team:
                previous = None
                continue
            # These are exact arrangement intervals, so midpoint ownership
            # represents both sides without numerical offset sampling.
            draw_circle = circle[:4]+(inner_team, circle[5])
            if previous is not None and previous[0] == draw_circle and abs(previous[2]-a) < EPS:
                result[-1] = previous = (draw_circle, previous[1], b)
            else:
                previous = (draw_circle, a, b)
                result.append(previous)
    return result


def polylines_from_arcs(arcs, step=1.0, max_segments=1024):
    # Budget includes mandatory end points of each visible arc. Typical 7-cloud
    # smoke uses about 250 segments at 1 m. Increase step for large sets.
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
