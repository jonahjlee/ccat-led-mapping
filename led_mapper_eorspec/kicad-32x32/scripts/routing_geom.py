"""Routing geometry for the LED array (pure Python, no pcbnew), in mm relative to the array centre.

Everything is computed for the bottom network (map row r -> board row 16+r) and mirrored
through the array centre for the top network (which is placed rotated 180 degrees).

Per pair cell (r, k), LEDs at LED cols 2k (left) and 2k+1 (right), pads read [h v][v h]:
  v-via: cell centre, DY below the row; both inner (v) pads stub to it.
  h-vias: in the gaps between cells, DY above the row. Adjacent cells with the same h net
          share one via at the gap centre; otherwise each cell gets its own via, offset
          OFF towards itself. Every pad stub is the same length except at those offset vias.
Layers:
  F.Cu  pad stubs only
  In1   horizontal row runs (through the h-vias); C bypasses and C corners; edge-band lanes
  In2   60-degree column runs (through the v-vias)
  B.Cu  A-chain links, B corners, A/B links between the grid and the edge-band lanes
Links (m = 1..8, BR = bottom-right quadrant, diagonal cell of BR row m is (7+m, 7+m)):
  A chain   A_(m+1): v-via of diag m  -> h-via of diag m+1 (one row down), B.Cu
  A links   (edge_bands only) A_m main row right end -> right edge band -> diag m (row 7+m);
            A_1 also -> v-via of diag 8. B.Cu stubs + In1 lanes along the right edge.
  B links   (edge_bands only) B_m main column bottom -> outer edge band -> B_m BR column, m=1..7
            Without edge bands these A and B pieces are left unconnected for manual routing.
  B corner  B_m BR row run end -> B_m BR column top, B.Cu; B_8 joins its row run to its main column
  C bypass  C_m row run skips over the B_m cells + diag, In1, in the channel above row 7+m,
            joined to C_m's column end (C corner).
"""
import math
from collections import defaultdict

import charlie_map as cm

P = cm.PITCH
ROW_H = cm.ROW_H
CH = ROW_H / 2          # mid-channel offset from a row
DY = 0.5                # via offset from the row line
OFF = 0.3               # via offset from the gap centre when two different nets share a gap
PAD_X = 0.20            # pad centre offset from the LED centre
LANE0, LANE_P = 0.6, 0.45   # edge-band lanes: first offset and pitch (mm)
BOT0 = 0.9                  # outer band: first lane below the last row's v-vias

F, IN1, IN2, B = "F.Cu", "In1.Cu", "In2.Cu", "B.Cu"


def led_xy(r, c):
    return cm.board_xy(16 + r, c)


def ry(r):
    return led_xy(r, 0)[1]


def cell_cx(r, k):
    return led_xy(r, 2 * k)[0] + P / 2


def h_net(r, k):
    return cm.cell_nets(r, k)[0]


def v_net(r, k):
    return cm.cell_nets(r, k)[1]


def vvia(r, k):
    return (cell_cx(r, k), ry(r) + DY)


def hvia(r, k, side):
    """h-via used by cell (r, k) in its left (side=-1) or right (side=+1) gap."""
    g = cell_cx(r, k) + side * P
    nb = k + side
    shared = 0 <= nb < cm.CELL_COLS and h_net(r, nb) == h_net(r, k)
    off = 0.0 if (shared or not 0 <= nb < cm.CELL_COLS) else -side * OFF
    return (g + off, ry(r) - DY)


class Geometry:
    def __init__(self):
        self.tracks = []    # (layer, net, [(x, y), ...])
        self.vias = {}      # rounded (x, y) -> (net, (x, y))

    def track(self, layer, net, *pts):
        self.tracks.append((layer, net, list(pts)))

    def via(self, net, pt):
        key = (round(pt[0], 4), round(pt[1], 4))
        old = self.vias.get(key)
        assert old is None or old[0] == net, f"via clash at {key}: {old[0]} vs {net}"
        self.vias[key] = (net, pt)


def build(edge_bands: bool = False) -> Geometry:
    """edge_bands=True adds the A/B links routed outside the LED area (off by default)."""
    g = Geometry()
    R, K = cm.CELL_ROWS, cm.CELL_COLS

    # vias + F.Cu stubs
    for r in range(R):
        for k in range(K):
            h, v = h_net(r, k), v_net(r, k)
            lx = led_xy(r, 2 * k)[0]
            y = ry(r)
            hl, hr, vv = hvia(r, k, -1), hvia(r, k, +1), vvia(r, k)
            for net, pt in ((h, hl), (h, hr), (v, vv)):
                g.via(net, pt)
            g.track(F, h, (lx - PAD_X, y), hl)
            g.track(F, v, (lx + PAD_X, y), vv)
            g.track(F, v, (lx + P - PAD_X, y), vv)
            g.track(F, h, (lx + P + PAD_X, y), hr)

    # In1 row runs
    for r in range(R):
        k0 = 0
        for k in range(1, K + 1):
            if k == K or h_net(r, k) != h_net(r, k0):
                g.track(IN1, h_net(r, k0), hvia(r, k0, -1), hvia(r, k - 1, +1))
                k0 = k

    # In2 column runs
    for k in range(K):
        r0 = 0
        for r in range(1, R + 1):
            if r == R or v_net(r, k) != v_net(r0, k):
                if r - 1 > r0:
                    g.track(IN2, v_net(r0, k), vvia(r0, k), vvia(r - 1, k))
                r0 = r

    for m in range(1, 9):
        rd = 7 + m                      # BR row of diag m
        y = ry(rd)
        A, Bm, C = m, 8 + m, 16 + m

        # A chain: A_(m+1) = v of diag m -> h-via (left gap) of diag m+1
        if m < 8:
            s = vvia(rd, rd)
            e = hvia(rd + 1, rd + 1, -1)
            g.track(B, m + 1, s, (s[0] + 0.405, y + CH), (e[0], y + CH), e)

        # C bypass (+ corner): In1 in the channel above row rd
        start = hvia(rd, 7, +1)                       # end of C_m's left run
        corner = vvia(rd - 1, rd)                     # bottom of C_m's column run
        path = [start, (start[0], y - CH)]
        if m < 8:
            end = hvia(rd, rd + 1, -1)                # start of C_m's right run
            path += [(end[0], y - CH), end]
        else:
            path += [(corner[0] + 0.405, y - CH)]
        g.track(IN1, C, *path)
        g.track(IN1, C, corner, (corner[0] + 0.405, y - CH))

        # B corner: B_m row run end -> B_m BR column top (B.Cu)
        if 2 <= m <= 7:
            g.track(B, Bm, hvia(rd, rd - 1, +1), vvia(rd + 1, rd))
        if m == 8:
            s = vvia(15, 7)                           # bottom of B_8's main column
            e = hvia(15, 8, -1)                       # start of B_8's row run
            g.track(B, Bm, s, (e[0], s[1]), e)

    if edge_bands:
        _right_band(g)
        _outer_band(g)
    return g


def _edge_x(y):
    """x of the right edge reference line (through the row-end h-vias) at height y."""
    x0, y0 = hvia(0, 15, +1)
    return x0 - (y - y0) * (P / 2) / ROW_H


def _lane_x(n, y):
    return _edge_x(y) + (LANE0 + (n - 1) * LANE_P) / math.sin(math.radians(60))


def _right_band(g):
    links = [(m, m, 7 + m) for m in range(1, 9)] + [(1, 9, None)]   # (A index, lane, target diag row)
    for a, lane, rd in links:
        ex = hvia(a - 1, 15, +1)                      # right end of A_a's main row
        top = (_lane_x(lane, ex[1]), ex[1])
        g.track(B, a, ex, top)
        g.via(a, top)
        if rd is not None:
            ye = ry(rd) - CH
            bot = (_lane_x(lane, ye), ye)
            tgt = hvia(rd, rd, +1)
            g.track(B, a, bot, (tgt[0], ye), tgt)
        else:                                          # A_1 -> v-via of the corner cell (diag 8)
            tgt = vvia(15, 15)
            bot = (_lane_x(lane, tgt[1]), tgt[1])
            g.track(B, a, bot, tgt)
        g.track(IN1, a, top, bot)
        g.via(a, bot)


def _outer_band(g):
    y15 = ry(15) + DY
    for m in range(1, 8):
        net = 8 + m
        s, e = vvia(15, m - 1), vvia(15, 7 + m)
        ly = y15 + BOT0 + (m - 1) * LANE_P
        g.track(B, net, s, (s[0], ly))
        g.track(IN1, net, (s[0], ly), (e[0], ly))
        g.track(B, net, (e[0], ly), e)
        g.via(net, (s[0], ly))
        g.via(net, (e[0], ly))


def mirrored(g: Geometry):
    """(tracks, vias) for both networks: bottom as built, top mirrored through the centre."""
    tracks, vias = [], []
    for sgn in (1, -1):
        for layer, net, pts in g.tracks:
            tracks.append((layer, net, [(sgn * x, sgn * y) for x, y in pts]))
        for net, (x, y) in g.vias.values():
            vias.append((net, (sgn * x, sgn * y)))
    return tracks, vias


def check_connectivity(g: Geometry):
    """Each net in the bottom network should form one island joining all its pads."""
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    key = lambda net, pt: (net, round(pt[0], 3), round(pt[1], 3))
    vias_at = defaultdict(list)
    for net, pt in g.vias.values():
        vias_at[(round(pt[0], 3), round(pt[1], 3))].append(net)
    pads = []
    for r in range(cm.CELL_ROWS):
        for k in range(cm.CELL_COLS):
            lx, y = led_xy(r, 2 * k)
            h, v = h_net(r, k), v_net(r, k)
            pads += [(h, (lx - PAD_X, y)), (v, (lx + PAD_X, y)), (v, (lx + P - PAD_X, y)), (h, (lx + P + PAD_X, y))]
    # tracks connect their consecutive points; points that land on a via or on another
    # track's vertex join (all vias are through vias, so layer does not matter at vias)
    for layer, net, pts in g.tracks:
        for a, b in zip(pts, pts[1:]):
            union(key(net, a), key(net, b))
    # mid-track pickups: runs pass through intermediate vias; track ends can land mid-track
    points = defaultdict(set)
    for vk, nets in vias_at.items():
        for n in nets:
            points[n].add(vk)
    for layer, net, pts in g.tracks:
        points[net].update((round(p[0], 3), round(p[1], 3)) for p in (pts[0], pts[-1]))
    for layer, net, pts in g.tracks:
        for a, b in zip(pts, pts[1:]):
            for p in points[net]:
                if _on_segment(p, a, b):
                    union(key(net, p), key(net, a))
    roots = defaultdict(set)
    for net, pt in pads:
        roots[net].add(find(key(net, pt)))
    return {cm.net_name(n): len(s) for n, s in sorted(roots.items())}


def _on_segment(p, a, b, tol=1e-3):
    (px, py), (ax, ay), (bx, by) = p, a, b
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if abs(cross) > tol * max(1e-9, math.hypot(bx - ax, by - ay)):
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    return -tol <= dot <= (bx - ax) ** 2 + (by - ay) ** 2 + tol


if __name__ == "__main__":
    geo = build()
    islands = check_connectivity(geo)
    bad = {n: c for n, c in islands.items() if c != 1}
    print(f"{len(geo.tracks)} tracks, {len(geo.vias)} vias per network")
    print("islands per net (bottom network):", "all 1" if not bad else bad)
    full = check_connectivity(build(edge_bands=True))
    print("with edge bands:", "all 1" if all(c == 1 for c in full.values()) else full)
