"""Structured routing for v2, following the schematic's matrix blocks.

Every LED centre and via sits on a triangular lattice of spacing s = P/8 (0.261 mm). All
joins run along that lattice, in its three directions only (0, 60, 120 degrees).

Per network (16 rows x 32 columns) the schematic has three blocks:
  left block   columns 0-22: cathode rows (P24..P09), anode columns stepping at the diagonal
  right-upper  columns 23-31, rows 0-7: a 9x8 matrix (cathodes P08..P01, anodes P01-P10)
  right-lower  columns 23-31, rows 8-15: straight anode columns P11-P19, cathodes P08..P01

Routing:
  1. straight runs  In1 cathode rows, In2 anode columns (route_leds.straight_runs)
  2. rails (In1)    each right-block cathode row (P01-P08) runs back along the lane under its
                    LED row to its own full-height anode column in the left block
  3. bridges (B.Cu) each right-block anode column (P09-P19) runs back along a mid-row lane
                    (P19: the lane under row 8) to its column in the left block
  4. joins          diagonal junctions (cathode row <-> its anode columns) and seam steps
                    (column continues one column right into network 2): shortest path on
                    the lattice with a bend penalty and no sharp turns, closest island pair
                    first, layers tried in the order In2, In1, B.Cu
Rails and bridges have fixed shapes: 60-degree two-step stubs from the vias onto the lane.
  5. centring       S-shaped joins (both ends turn the same way) get their middle segment slid
                    sideways to the centre of the gap it runs through (most clearance both sides)

Run with KiCad's Python, board closed in KiCad (--dry-run computes without writing):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" kicad-32x32-v2/scripts/route_structured.py
"""
import heapq
import math
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_leds as rl             # noqa: E402  (first: v1 has a module of the same name)
import lane_router as lr            # noqa: E402
import place_vias as pv             # noqa: E402
import set_design_rules as dr       # noqa: E402

GROUP = "led_routing"
P, H = pv.P, pv.H
S = P / 8
SQ = math.sqrt(3) / 2
DIRS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]   # 0, 60, 120, 180, 240, 300 deg (y down)
BEND, MAX_EXPAND = 4.0, 60000
JOIN_LAYERS = ("In2.Cu", "In1.Cu", "B.Cu")


class Lat:
    def __init__(self, x0, y0):
        self.x0, self.y0 = x0, y0

    def pt(self, i, j):
        return (self.x0 + S * (i + j / 2), self.y0 + S * SQ * j)

    def ij(self, p):
        j = round((p[1] - self.y0) / (S * SQ))
        i = round((p[0] - self.x0) / S - j / 2)
        return i, j


def load(board):
    mm = pcbnew.ToMM
    vias = [(t.GetNetname(), tuple(mm(t.GetPosition()))) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    via_at = {(round(p[0], 3), round(p[1], 3)): (n, p) for n, p in vias}
    stubs = [("F.Cu", t.GetNetname(), [tuple(mm(t.GetStart())), tuple(mm(t.GetEnd()))])
             for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.F_Cu]
    leds, grid = {}, {}
    pos = {fp.GetReference(): mm(fp.GetPosition()) for fp in board.GetFootprints() if fp.GetReference().startswith("D")}
    x1, y1 = pos["D1"]
    for ref, (x, y) in pos.items():
        kv = via_at[(round(x + pv.OFFSETS["1"][0], 3), round(y + pv.OFFSETS["1"][1], 3))]
        av = via_at[(round(x + pv.OFFSETS["2"][0], 3), round(y + pv.OFFSETS["2"][1], 3))]
        leds[ref] = (x, y, kv[1], kv[0], av[1], av[0])
        R = round((y - y1) / H)
        C = round((x - x1 + R * P / 2) / P)
        grid[(R, C)] = {"xy": (x, y), "kv": kv[1], "K": kv[0], "av": av[1], "A": av[0]}
    return vias, stubs, leds, grid, Lat(x1, y1)


def add(lat, p, di, dj, n=1):
    i, j = lat.ij(p)
    return lat.pt(i + di * n, j + dj * n)


def rails_and_bridges(grid, lat):
    rails, bridges = [], []
    for b in (0, 16):
        for R in range(16):
            k = 8 - R if R < 8 else 16 - R
            src, dst = grid[(b + R, 23)], grid[(b + R, k - 1)]
            assert src["K"] == dst["A"] == f"/P{k}", (b + R, k, src["K"], dst["A"])
            a = src["kv"]
            a1 = add(lat, a, -1, 1, 2)                     # down-left onto the row line
            z = dst["av"]
            z1 = add(lat, z, 0, -1, 2)                     # up-left from the anode via onto the row line
            rails.append(("In1.Cu", src["K"], [a, a1, z1, z]))
        spec = [(n, 26 - n, 12 + n, n - 2, "mid") for n in range(11, 19)] + [(19, 8, 31, 17, "row"),
                (9, 6, 30, 8, "mid"), (10, 7, 31, 9, "mid")]
        for n, R, cr, cl, lane in spec:
            src, dst = grid[(b + R, cr)], grid[(b + R, cl)]
            assert src["A"] == dst["A"] == f"/P{n}", (n, src["A"], dst["A"])
            a, z = src["av"], dst["av"]
            if lane == "mid":                              # two steps down onto the mid-row lane
                a1, z1 = add(lat, a, -1, 1, 2), add(lat, z, 0, 1, 2)
            else:                                          # two steps up onto the row line
                a1, z1 = add(lat, a, 0, -1, 2), add(lat, z, 1, -1, 2)
            bridges.append(("B.Cu", src["A"], [a, a1, z1, z]))
    return rails, bridges


def obstacles(layer, tracks, vias):
    obs = lr.Obstacles()
    for n, p in vias:
        obs.add_via(n, p)
    for lyr, n, pts in tracks:
        if lyr == layer:
            for a, b in zip(pts, pts[1:]):
                obs.add_seg(n, a, b)
    return obs


def lattice_path(lat, obs, net, sources, targets):
    """A* on the lattice from any source via to any target via; bends cost BEND, no
    sharp (120-degree) turns. Returns a list of points (corners only) or None."""
    tset = {lat.ij(p) for p in targets}
    tx = [lat.pt(*t) for t in tset]
    h = lambda ij: min(math.dist(lat.pt(*ij), t) for t in tx) / S
    pq, best, prev, cnt = [], {}, {}, 0
    for p in sources:
        ij = lat.ij(p)
        for d in range(6):
            st = (ij, d)
            best[st] = 0.0
            heapq.heappush(pq, (h(ij), 0.0, cnt, st)); cnt += 1
    while pq and cnt < MAX_EXPAND:
        f, g, _, st = heapq.heappop(pq)
        if g > best.get(st, 1e18):
            continue
        ij, d = st
        if ij in tset and st in prev:
            path = [st]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            pts = [lat.pt(*s[0]) for s in reversed(path)]
            dirs = [s[1] for s in reversed(path)]
            out = [pts[0]]
            for k in range(1, len(pts) - 1):
                if dirs[k + 1] != dirs[k]:
                    out.append(pts[k])
            out.append(pts[-1])
            return out
        for nd in (d, (d + 1) % 6, (d - 1) % 6) if st in prev else range(6):
            di, dj = DIRS[nd]
            nij = (ij[0] + di, ij[1] + dj)
            ng = g + 1.0 + (BEND if (st in prev and nd != d) else 0.0)
            nst = (nij, nd)
            if ng >= best.get(nst, 1e18):
                continue
            if not obs.clear(net, lat.pt(*ij), lat.pt(*nij)):
                continue
            best[nst] = ng
            prev[nst] = st
            heapq.heappush(pq, (ng + h(nij), ng, cnt, nst)); cnt += 1
    return None


def joins(lat, tracks, vias, verbose=True):
    """Join remaining islands: closest island pair first, lattice paths, In2 > In1 > B.Cu."""
    new = []
    while True:
        uf, key = lr.islands(tracks + new, vias)
        groups = defaultdict(lambda: defaultdict(list))
        for n, p in vias:
            groups[n][uf.find(key(n, p))].append(p)
        pairs = []
        for n, isl in groups.items():
            isl = list(isl.values())
            for a in range(len(isl)):
                for b in range(a + 1, len(isl)):
                    d, pa, pb = min((math.dist(p, q), p, q) for p in isl[a] for q in isl[b])
                    pairs.append((d, n, isl[a], isl[b]))
        if not pairs:
            return new, {}
        pairs.sort(key=lambda t: (round(t[0], 3), t[1]))
        made = False
        for d, n, A, B in pairs:
            near_a = [p for p in A if min(math.dist(p, q) for q in B) < d + 3]
            near_b = [q for q in B if min(math.dist(q, p) for p in A) < d + 3]
            for layer in JOIN_LAYERS:
                obs = obstacles(layer, tracks + new, vias)
                path = lattice_path(lat, obs, n, near_a, near_b)
                if path:
                    new.append((layer, n, path))
                    made = True
                    break
            if made:
                break
        if not made:
            left = {n: len(isl) for n, isl in groups.items() if len(isl) > 1}
            return new, left


def min_clearance(obs, net, a, b):
    """Smallest edge-to-edge gap from segment a-b (track) to other-net vias and tracks."""
    best = 1e9
    for c in obs._cells(a, b, 1.5):
        for n, p in obs.vias.get(c, ()):
            if n != net:
                best = min(best, lr._pt_seg(p, a, b) - lr.VIA_R - lr.HALF_W)
        for n, s0, s1, _ in obs.segs.get(c, ()):
            if n != net:
                best = min(best, lr._seg_seg(a, b, s0, s1) - 2 * lr.HALF_W)
    return best


def centre_s_joins(js, base, vias):
    """S-shaped joins (end segments parallel and pointing the same way, middle segment at an
    angle): slide the middle segment sideways, trading length between the two ends, to the
    position with the most clearance on both sides, i.e. the centre of the gap it runs through."""
    out, changed = list(js), 0
    for idx, (layer, net, pts) in enumerate(out):
        if len(pts) != 4:
            continue
        a, b, c, d = pts
        u1 = (b[0] - a[0], b[1] - a[1])
        u3 = (d[0] - c[0], d[1] - c[1])
        l1, l3 = math.hypot(*u1), math.hypot(*u3)
        if l1 < 1e-6 or l3 < 1e-6:
            continue
        u = (u1[0] / l1, u1[1] / l1)
        if abs(u[0] * u3[0] / l3 + u[1] * u3[1] / l3 - 1) > 1e-6:
            continue                                   # ends not parallel: not an S
        v = (c[0] - b[0], c[1] - b[1])
        others = [t for k, t in enumerate(out) if k != idx]
        obs = obstacles(layer, base + others, vias)
        total = l1 + l3
        best = None
        steps = int(total / 0.01)
        for k in range(1, steps):
            t = total * k / steps
            p1 = (a[0] + u[0] * t, a[1] + u[1] * t)
            p2 = (p1[0] + v[0], p1[1] + v[1])
            segs = [(a, p1), (p1, p2), (p2, d)]
            if not all(obs.clear(net, s, e) for s, e in segs):
                continue
            score = (round(min_clearance(obs, net, p1, p2), 3), -abs(t - total / 2))
            if best is None or score > best[0]:
                best = (score, [a, p1, p2, d])
        if best and max(abs(best[1][1][0] - b[0]), abs(best[1][1][1] - b[1])) > 1e-3:
            out[idx] = (layer, net, best[1])
            changed += 1
    return out, changed


def build(board):
    vias, stubs, leds, grid, lat = load(board)
    runs = rl.straight_runs(leds)
    rails, bridges = rails_and_bridges(grid, lat)
    fixed = rails + bridges
    for layer, net, pts in fixed:
        obs = obstacles(layer, stubs + runs + [t for t in fixed if t[2] is not pts], vias)
        for a, b in zip(pts, pts[1:]):
            assert obs.clear(net, a, b), f"fixed {layer} track for {net} not clear at {a}->{b}"
    base = stubs + runs + fixed
    js, left = joins(lat, base, vias)
    js, n_centred = centre_s_joins(js, base, vias)
    print(f"centred {n_centred} S-shaped joins in their gaps")
    return runs, rails, bridges, js, left


def main(dry_run=False):
    pcb = pv.PCB_FILE
    if not dry_run and pcb.with_name(f"~{pcb.name}.lck").exists():
        sys.exit(f"{pcb.name} is open in KiCad; close it first.")
    board = pcbnew.LoadBoard(str(pcb))
    for grp in list(board.Groups()):
        if grp.GetName() == GROUP:
            for item in list(grp.GetItems()):
                board.Delete(item)
            board.Delete(grp)
    runs, rails, bridges, js, left = build(board)
    by_layer = defaultdict(int)
    for layer, _, _ in js:
        by_layer[layer] += 1
    print(f"{len(runs)} straight runs, {len(rails)} In1 rails, {len(bridges)} B.Cu bridges, "
          f"{len(js)} lattice joins {dict(by_layer)}; still split: {left or 'none'}")
    new = runs + rails + bridges + js
    if dry_run:
        return runs, rails, bridges, js
    group = pcbnew.PCB_GROUP(board)
    group.SetName(GROUP)
    board.Add(group)
    width = pcbnew.FromMM(dr.TRACK)
    nets = {}
    for layer, net, pts in new:
        nets.setdefault(net, board.FindNet(net))
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
            t.SetWidth(width)
            t.SetLayer(rl.LAYERS[layer])
            t.SetNet(nets[net])
            board.Add(t)
            group.AddItem(t)
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb), board)
    print(f"wrote group '{GROUP}' to {pcb.name}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
