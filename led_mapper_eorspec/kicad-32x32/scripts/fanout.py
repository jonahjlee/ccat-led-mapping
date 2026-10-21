"""Fan-out: connect each net P01-P24 to a pad of J1 on B.Cu, choosing the pin mapping.

The pin-to-net mapping is free (the Arduino code uses a lookup table), so each net is
routed from whichever of its vias is closest to whichever J1 pad is still free. The
result is written to kicad-32x32/connector_map.csv (pin -> net), which gen_schematic.py
and place_connector.py read, so the schematic, board and firmware table stay in sync.

Router: a 0.05 mm grid over the connector and the lower-right corner of the array.
Each cell records which net's copper (vias, B.Cu tracks, J1 pads) is within clearance;
cells near two different nets are blocked for everyone. Nets are routed nearest first,
each with A* from all its vias to any free pad, then straightened into as few segments
as stay clear. Tracks go into the group "fanout" (re-running replaces only that group).

Run with KiCad's Python, with the board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" scripts/fanout.py
"""
import csv
import heapq
import math
import sys
from pathlib import Path

import numpy as np
import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charlie_map as cm            # noqa: E402
import gen_schematic as gs          # noqa: E402
import place_leds as pl             # noqa: E402
import set_design_rules as dr       # noqa: E402

GROUP = "fanout"
MAP_CSV = cm.CSV_PATH.with_name("connector_map.csv")
RES = 0.05                          # grid step (mm)
MARGIN_LEFT, MARGIN = 22.0, 4.0     # grid extent around J1 (mm)
HALF_W = dr.TRACK / 2
CLR = dr.CLEARANCE
FREE, MULTI, PAD0 = -1, -2, 1000    # owner codes: free, blocked, PAD0 + pad index


def mm(v):
    return pcbnew.ToMM(v)


class Grid:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.nx, self.ny = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
        self.owner = np.full((self.ny, self.nx), FREE, dtype=np.int32)
        xs = x0 + np.arange(self.nx) * RES
        ys = y0 + np.arange(self.ny) * RES
        self.X, self.Y = np.meshgrid(xs, ys)

    def cell(self, x, y):
        return int(round((y - self.y0) / RES)), int(round((x - self.x0) / RES))

    def xy(self, c):
        return self.x0 + c[1] * RES, self.y0 + c[0] * RES

    def _window(self, xa, ya, xb, yb, pad):
        i0 = max(0, int((min(ya, yb) - pad - self.y0) / RES))
        i1 = min(self.ny, int((max(ya, yb) + pad - self.y0) / RES) + 2)
        j0 = max(0, int((min(xa, xb) - pad - self.x0) / RES))
        j1 = min(self.nx, int((max(xa, xb) + pad - self.x0) / RES) + 2)
        return slice(i0, i1), slice(j0, j1)

    def _paint(self, win, mask, code):
        sub = self.owner[win]
        cur = sub[mask]
        sub[mask] = np.where((cur == FREE) | (cur == code), code, MULTI)

    def paint_seg(self, a, b, dist, code):
        win = self._window(a[0], a[1], b[0], b[1], dist)
        X, Y = self.X[win], self.Y[win]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = np.zeros_like(X) if L2 == 0 else np.clip(((X - a[0]) * dx + (Y - a[1]) * dy) / L2, 0, 1)
        d = np.hypot(X - a[0] - t * dx, Y - a[1] - t * dy)
        self._paint(win, d < dist, code)

    def paint_rect(self, cx, cy, w, h, ang_deg, dist, code):
        r = math.hypot(w, h) / 2 + dist
        win = self._window(cx, cy, cx, cy, r)
        X, Y = self.X[win] - cx, self.Y[win] - cy
        a = math.radians(ang_deg)
        u = X * math.cos(a) - Y * math.sin(a)          # into the pad frame (KiCad y down, CCW)
        v = X * math.sin(a) + Y * math.cos(a)
        du = np.maximum(np.abs(u) - w / 2, 0)
        dv = np.maximum(np.abs(v) - h / 2, 0)
        self._paint(win, np.hypot(du, dv) < dist, code)


def route_net(g, net, sources, targets, free_pads):
    """A* from source cells to any cell owned by a free pad. Returns (cells, pad index)."""
    ok = lambda o, here: o == FREE or o == net or (o >= PAD0 and (o - PAD0) in free_pads
                                                      and (here < PAD0 or here == o))
    tx = [(x, y) for p, (x, y) in targets.items() if p in free_pads]
    h = lambda c: min(math.hypot(g.xy(c)[0] - x, g.xy(c)[1] - y) for x, y in tx) / RES
    dist, prev, pq = {}, {}, []
    for s in sources:
        if 0 <= s[0] < g.ny and 0 <= s[1] < g.nx:
            dist[s] = 0.0
            heapq.heappush(pq, (h(s), 0.0, s))
    steps = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1),
             (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
    while pq:
        f, d, c = heapq.heappop(pq)
        if d > dist.get(c, 1e18):
            continue
        here = g.owner[c]
        if here >= PAD0 and (here - PAD0) in free_pads:
            path = [c]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return path[::-1], here - PAD0
        for di, dj, w in steps:
            n = (c[0] + di, c[1] + dj)
            if not (0 <= n[0] < g.ny and 0 <= n[1] < g.nx):
                continue
            if not ok(g.owner[n], here):
                continue
            nd = d + w
            if nd < dist.get(n, 1e18):
                dist[n] = nd
                prev[n] = c
                heapq.heappush(pq, (nd + h(n), nd, n))
    return None, None


def clear_line(g, net, a, b, pad_code):
    """True if the straight segment a-b (mm) only crosses cells usable by `net`."""
    n = max(2, int(math.dist(a, b) / (RES / 2)))
    for k in range(n + 1):
        x = a[0] + (b[0] - a[0]) * k / n
        y = a[1] + (b[1] - a[1]) * k / n
        o = g.owner[g.cell(x, y)]
        if not (o == FREE or o == net or o == pad_code):
            return False
    return True


def straighten(g, net, pts, pad_code):
    out, i = [pts[0]], 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and not clear_line(g, net, pts[i], pts[j], pad_code):
            j -= 1
        out.append(pts[j])
        i = j
    return out


def main():
    pcb = pl.PCB_FILE
    if pcb.with_name(f"~{pcb.name}.lck").exists():
        sys.exit(f"{pcb.name} is open in KiCad; close it first.")
    board = pcbnew.LoadBoard(str(pcb))
    for grp in list(board.Groups()):
        if grp.GetName() == GROUP:
            for item in list(grp.GetItems()):
                board.Delete(item)
            board.Delete(grp)

    j1 = board.FindFootprintByReference(gs.CONN_REF)
    bb = j1.GetBoundingBox(False)
    x0, y0 = mm(bb.GetX()) - MARGIN_LEFT, mm(bb.GetY()) - MARGIN
    x1, y1 = mm(bb.GetRight()) + MARGIN, mm(bb.GetBottom()) + MARGIN
    g = Grid(x0, y0, x1, y1)

    nets = {n: board.FindNet(cm.net_name(n)) for n in range(1, cm.NUM_NETS + 1)}
    code_of = {nets[n].GetNetCode(): n for n in nets}
    vias = defaultdict_list()
    for t in board.GetTracks():
        n = code_of.get(t.GetNetCode())
        if n is None:
            continue
        if t.GetClass() == "PCB_VIA":
            p = mm(t.GetPosition())
            if x0 - 1 < p[0] < x1 + 1 and y0 - 1 < p[1] < y1 + 1:
                g.paint_seg(p, p, mm(t.GetWidth(pcbnew.B_Cu)) / 2 + CLR + HALF_W, n)
                vias[n].append(p)
        elif t.GetLayer() == pcbnew.B_Cu:
            g.paint_seg(mm(t.GetStart()), mm(t.GetEnd()), mm(t.GetWidth()) / 2 + CLR + HALF_W, n)

    pads = {}
    for p in j1.Pads():
        k = int(p.GetNumber())
        cx, cy = mm(p.GetPosition())
        w, h = mm(p.GetSize(pcbnew.B_Cu).x), mm(p.GetSize(pcbnew.B_Cu).y)
        ang = p.GetOrientationDegrees()
        pads[k] = (cx, cy, w, h, ang)
        g.paint_rect(cx, cy, w, h, ang, CLR + HALF_W, PAD0 + k)

    targets = {k: (v[0], v[1]) for k, v in pads.items()}
    order = sorted(nets, key=lambda n: min((math.dist(v, t) for v in vias[n] for t in targets.values()),
                                           default=1e9))
    free_pads = set(pads)
    result, assignment = [], {}
    for n in order:
        srcs = [g.cell(*v) for v in vias[n]]
        cells, pad = route_net(g, n, srcs, targets, free_pads)
        if cells is None:
            print(f"  {cm.net_name(n)}: no route found")
            continue
        free_pads.discard(pad)
        assignment[pad] = n
        pts = [g.xy(c) for c in cells]
        start = min(vias[n], key=lambda v: math.dist(v, pts[0]))
        pts[0] = start
        pts[-1] = targets[pad]
        pts = straighten(g, n, pts, PAD0 + pad)
        cx, cy, w, h, ang = pads[pad]
        g.paint_rect(cx, cy, w, h, ang, CLR + HALF_W, n)       # pad now belongs to the net
        for a, b in zip(pts, pts[1:]):
            g.paint_seg(a, b, 2 * HALF_W + CLR, n)
        result.append((n, pts))

    group = pcbnew.PCB_GROUP(board)
    group.SetName(GROUP)
    board.Add(group)
    for n, pts in result:
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
            t.SetWidth(pcbnew.FromMM(dr.TRACK))
            t.SetLayer(pcbnew.B_Cu)
            t.SetNet(nets[n])
            board.Add(t)
            group.AddItem(t)
    for k, n in assignment.items():
        j1.FindPadByNumber(str(k)).SetNet(nets[n])
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb), board)

    with open(MAP_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pin", "net"])
        for k in sorted(assignment):
            w.writerow([k, cm.net_name(assignment[k])])
    print(f"fan-out: {len(result)}/24 nets routed; pin map written to {MAP_CSV.name}")


def defaultdict_list():
    from collections import defaultdict
    return defaultdict(list)


if __name__ == "__main__":
    main()
