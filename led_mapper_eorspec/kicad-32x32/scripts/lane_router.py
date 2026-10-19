"""Join separate copper islands of the same net with lane tracks: 60-degree In2 tracks between
the columns first, then horizontal In1 tracks along the row lines and mid-row gaps.

In2 already holds the column runs (60-degree lines through the v-vias at cell centres).
Between two adjacent column lines is a corridor whose centre line passes through the
h-vias in the cell gaps. Lanes run parallel to the columns at fixed offsets (LANE_RES),
clear of the gap vias and the column tracks, and some continue across the seam so
they can also join the top and bottom networks.

A connection = via -> short horizontal jog -> straight 60-degree lane run -> jog -> via.
Candidates are tried most-constrained island pair first (then shortest) and
accepted only if they join two different
islands of the net and every segment clears all other-net vias and In2 copper
(including joins accepted earlier) by the board clearance.
"""
import math
from collections import defaultdict

import charlie_map as cm
import routing_geom as rg

# Lane positions, as x offsets (mm) from a bottom-network column line, repeating every
# 2 x pitch. The top network is mirrored, so its via lines sit 0.577 mm (= 1 mm x tan 30)
# sideways from the bottom network's: offsets 0.5-1.3 are clear in both halves (seam
# crossings), 2.9-3.7 only in the bottom half, 0.1 and 1.7 only in the top half.
# Every candidate is also checked against the real copper, so a wrong guess is just rejected.
LANE_RES = (0.1, 0.5, 0.9, 1.3, 1.7, 2.9, 3.3, 3.7)
VIA_R, HALF_W, CLR = 0.225, 0.05, 0.1
TAN30 = math.tan(math.radians(30))
CELL_W = 2 * cm.PITCH        # corridor repeat (mm, horizontal)
BIN = 1.0


def intercept(x, y):
    """Identifies the 60-degree line through (x, y): its x at y = 0."""
    return x + y * TAN30


class UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb
            return True
        return False


def islands(tracks, vias):
    """Union-find over via keys (net, x, y): vias joined by any track of their net."""
    uf = UF()
    key = lambda n, p: (n, round(p[0], 3), round(p[1], 3))
    pts_by_net = defaultdict(set)
    for n, p in vias:
        uf.find(key(n, p))
        pts_by_net[n].add((round(p[0], 3), round(p[1], 3)))
    for _, n, pts in tracks:
        pts_by_net[n].update((round(q[0], 3), round(q[1], 3)) for q in (pts[0], pts[-1]))
    for _, n, pts in tracks:
        for a, b in zip(pts, pts[1:]):
            uf.union(key(n, a), key(n, b))
            lo_x, hi_x = min(a[0], b[0]) - 0.01, max(a[0], b[0]) + 0.01
            lo_y, hi_y = min(a[1], b[1]) - 0.01, max(a[1], b[1]) + 0.01
            for q in pts_by_net[n]:
                if lo_x <= q[0] <= hi_x and lo_y <= q[1] <= hi_y and rg._on_segment(q, a, b):
                    uf.union(key(n, q), key(n, a))
    return uf, key


def _pt_seg(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _seg_seg(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return 0.0
    return min(_pt_seg(c, a, b), _pt_seg(d, a, b), _pt_seg(a, c, d), _pt_seg(b, c, d))


def _share_end(a, b, c, d, tol=1e-6):
    return any(math.dist(p, q) < tol for p in (a, b) for q in (c, d))


def _crosses(a, b, c, d, tol=1e-6):
    """Segments intersect with neither touching the other only at an end (a real X crossing)."""
    if _seg_seg(a, b, c, d) > tol:
        return False
    return not any(_pt_seg(p, *seg) < tol for p, seg in ((a, (c, d)), (b, (c, d)), (c, (a, b)), (d, (a, b))))


class Obstacles:
    """In2 copper (vias are through, so all vias count) in a coarse spatial hash."""

    def __init__(self):
        self.vias = defaultdict(list)
        self.segs = defaultdict(list)

    @staticmethod
    def _cells(a, b, pad):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for i in range(math.floor((x0 - pad) / BIN), math.floor((x1 + pad) / BIN) + 1):
            for j in range(math.floor((y0 - pad) / BIN), math.floor((y1 + pad) / BIN) + 1):
                yield i, j

    def add_via(self, net, p):
        for c in self._cells(p, p, 0):
            self.vias[c].append((net, p))

    def add_seg(self, net, a, b, join=False):
        for c in self._cells(a, b, 0):
            self.segs[c].append((net, a, b, join))

    def clear(self, net, a, b):
        need_v = VIA_R + HALF_W + CLR - 1e-4
        need_t = 2 * HALF_W + CLR - 1e-4
        for c in self._cells(a, b, 0.6):
            for n, p in self.vias.get(c, ()):
                if n != net and _pt_seg(p, a, b) < need_v:
                    return False
            for n, s0, s1, join in self.segs.get(c, ()):
                if n != net:
                    if _seg_seg(a, b, s0, s1) < need_t:
                        return False
                elif _crosses(a, b, s0, s1):
                    return False        # no crossing through same-net copper (T-junctions are fine)
        return True


def lane_options(x, y, col0):
    """(lane intercept, jog end x) for every lane within one pitch either side of a via."""
    c = intercept(x, y)
    base = col0 + math.floor((c - col0) / CELL_W) * CELL_W
    out = []
    for k in (-1, 0, 1):
        for r in LANE_RES:
            lane = base + k * CELL_W + r
            if 0.3 < abs(lane - c) < cm.PITCH + 0.01:
                out.append((round(lane, 3), x + (lane - c)))
    return out


def in2_options(x, y, col0):
    """In2: 60-degree lanes between the columns. -> (lane id, jog end, position along lane)"""
    return [(("in2", lane), (jx, y), y) for lane, jx in lane_options(x, y, col0)]


# In1: horizontal lanes on every LED row line (no vias there: they sit +/-DY off the row)
# and in the middle of every gap between rows. Board rows 0-31 relative to the array centre.
IN1_LANES = sorted([cm.board_xy(R, 0)[1] for R in range(32)] +
                   [cm.board_xy(R, 0)[1] + rg.CH for R in range(31)])


def in1_options(x, y, col0=None):
    """In1: horizontal lanes 0.3-0.6 mm above/below the via. -> (lane id, jog end, position)"""
    return [(("in1", round(ly, 3)), (x, ly), x) for ly in IN1_LANES if 0.3 < abs(ly - y) < 0.6]


def route(tracks, vias, layer=rg.IN2, options=in2_options, verbose=True):
    """Join islands of the same net with lane tracks on `layer`. Returns the new tracks."""
    uf, key = islands(tracks, vias)
    col0 = intercept(*rg.vvia(0, 0))
    lanes = defaultdict(list)       # lane -> [(pos, net, via_pt, jog_pt)]
    for n, p in vias:
        for lane, jog, pos in options(p[0], p[1], col0):
            lanes[lane].append((pos, n, p, jog))
    obs = Obstacles()
    for n, p in vias:
        obs.add_via(n, p)
    for lyr, n, pts in tracks:
        if lyr == layer:
            for a, b in zip(pts, pts[1:]):
                obs.add_seg(n, a, b)

    cands = []
    for lane, eps in lanes.items():
        by_net = defaultdict(list)
        for e in eps:
            by_net[e[1]].append(e)
        for n, es in by_net.items():
            es.sort(key=lambda e: e[0])
            for i in range(len(es)):
                for j in range(i + 1, len(es)):
                    a, b = es[i], es[j]
                    if uf.find(key(n, a[2])) != uf.find(key(n, b[2])):
                        cands.append((abs(b[0] - a[0]), lane, a, b))
    # most-constrained island pairs first (fewest alternatives), then shortest
    n_alt = defaultdict(int)
    pair = lambda c: tuple(sorted((uf.find(key(c[2][1], c[2][2])), uf.find(key(c[3][1], c[3][2])))))
    for c in cands:
        n_alt[pair(c)] += 1
    cands.sort(key=lambda c: (n_alt[pair(c)], c[0]))

    new_tracks = []
    for _, lane, a, b in cands:
        n = a[1]
        if uf.find(key(n, a[2])) == uf.find(key(n, b[2])):
            continue
        path = [a[2], a[3], b[3], b[2]]
        if not all(obs.clear(n, p, q) for p, q in zip(path, path[1:])):
            continue
        uf.union(key(n, a[2]), key(n, b[2]))
        for p, q in zip(path, path[1:]):
            obs.add_seg(n, p, q, join=True)
        new_tracks.append((layer, n, path))
    if verbose:
        remaining = defaultdict(set)
        for n, p in vias:
            remaining[n].add(uf.find(key(n, p)))
        left = {cm.net_name(n): len(s) for n, s in sorted(remaining.items()) if len(s) > 1}
        print(f"{layer} lanes: {len(new_tracks)} joins made; nets still split (islands): {left or 'none'}")
    return new_tracks


def route_l(tracks, vias, layer=rg.B, verbose=True):
    """Join remaining islands with one L-shaped track on `layer`: a horizontal lane run
    (In1 lane positions) from one via and a 60-degree lane run (In2 lane positions) into
    the other, meeting at a single corner. Shortest clear candidate per island pair first."""
    uf, key = islands(tracks, vias)
    col0 = intercept(*rg.vvia(0, 0))
    obs = Obstacles()
    for n, p in vias:
        obs.add_via(n, p)
    for lyr, n, pts in tracks:
        if lyr == layer:
            for a, b in zip(pts, pts[1:]):
                obs.add_seg(n, a, b)
    by_isl = defaultdict(lambda: defaultdict(list))
    for n, p in vias:
        by_isl[n][uf.find(key(n, p))].append(p)

    new_tracks = []
    for n, isl in sorted(by_isl.items()):
        if len(isl) < 2:
            continue
        cands = []
        groups = list(isl.values())
        for gi in range(len(groups)):
            for gj in range(len(groups)):
                if gi == gj:
                    continue
                for a in groups[gi]:                       # a: horizontal end
                    for _, ja, _ in in1_options(*a):
                        yh = ja[1]
                        for b in groups[gj]:               # b: 60-degree end
                            for (_, lane), jb, _ in in2_options(*b, col0):
                                cx = lane - yh * TAN30     # corner on the horizontal lane
                                path = [a, ja, (cx, yh), jb, b]
                                length = sum(math.dist(p, q) for p, q in zip(path, path[1:]))
                                cands.append((length, path))
        cands.sort(key=lambda c: c[0])
        for length, path in cands:
            a, b = path[0], path[-1]
            if uf.find(key(n, a)) == uf.find(key(n, b)):
                continue
            if all(obs.clear(n, p, q) for p, q in zip(path, path[1:])):
                uf.union(key(n, a), key(n, b))
                for p, q in zip(path, path[1:]):
                    obs.add_seg(n, p, q, join=True)
                new_tracks.append((layer, n, path))
    if verbose:
        remaining = defaultdict(set)
        for n, p in vias:
            remaining[n].add(uf.find(key(n, p)))
        left = {cm.net_name(n): len(s) for n, s in sorted(remaining.items()) if len(s) > 1}
        print(f"{layer} L-joins: {len(new_tracks)} made; nets still split (islands): {left or 'none'}")
    return new_tracks


def route_all(tracks, vias, verbose=True):
    """In2 lanes first, then In1 lanes, then B.Cu L-joins for what is left. Returns new tracks."""
    new = route(tracks, vias, rg.IN2, in2_options, verbose)
    new += route(tracks + new, vias, rg.IN1, in1_options, verbose)
    new += route_l(tracks + new, vias, rg.B, verbose)
    return new


if __name__ == "__main__":
    t, v = rg.mirrored(rg.build())
    before_uf, k = islands(t, v)
    split = defaultdict(set)
    for n, p in v:
        split[n].add(before_uf.find(k(n, p)))
    print("before:", {cm.net_name(n): len(s) for n, s in sorted(split.items())})
    for lyr, n, pts in route_all(t, v):
        print(f"  {lyr} {cm.net_name(n)}: ({pts[0][0]:6.2f}, {pts[0][1]:6.2f}) -> ({pts[-1][0]:6.2f}, {pts[-1][1]:6.2f})")
