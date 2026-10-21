"""Route the v2 LED array from the per-pad vias placed by place_vias.py.

1. Straight runs: In1 horizontal tracks through the cathode vias of neighbouring LEDs that
   share a cathode net (rows); In2 60-degree tracks through the anode vias of LEDs in
   consecutive rows of the same column that share an anode net (columns). Both networks are
   on one lattice (network 2 is a translated copy), so runs continue across the seam.
2. Joins for whatever is still split, with the lane router from scripts/lane_router.py:
   60-degree In2 lanes between the columns first, then horizontal In1 lanes, then one
   L-shaped B.Cu track (horizontal + 60-degree) per remaining join. Every candidate is
   checked against the real copper; joins never cross copper of their own net.
3. Straightening: each join is pulled tight (fewest straight segments between its two
   vias, ideally one) wherever that still clears all other copper on its layer.

Lanes (offsets chosen to clear the existing tracks and vias of the via lattice):
  In2: intercepts at anode column line + {0.30, 0.55, 1.54, 1.79} mm (period = LED pitch)
  In1: y at LED row line + {-0.20, +0.05, +0.85, +1.10} mm (period = row height)

Everything goes into the group "led_routing" (re-running replaces only that group).

Run with KiCad's Python, with the board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" kicad-32x32-v2/scripts/route_leds.py
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lane_router as lr            # noqa: E402
import place_vias as pv             # noqa: E402
import set_design_rules as dr       # noqa: E402

GROUP = "led_routing"
P, H = pv.P, pv.H
T30 = math.tan(math.radians(30))
IN2_OFFSETS = (0.30, 0.55, 1.54, 1.79)
IN1_OFFSETS = (-0.20, 0.05, 0.85, 1.10)
LAYERS = {"F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}


class Lattice:
    """Lane positions derived from one LED's position (all LEDs share one lattice)."""

    def __init__(self, led_x, led_y):
        ax, ay = led_x + pv.OFFSETS["2"][0], led_y + pv.OFFSETS["2"][1]
        self.col0 = ax + ay * T30          # intercept of an anode column line
        self.row0 = led_y                  # an LED row line

    def in2(self, x, y, _=None):
        c = x + y * T30
        base = self.col0 + math.floor((c - self.col0) / P) * P
        out = []
        for k in (-1, 0, 1):
            for off in IN2_OFFSETS:
                lane = base + k * P + off
                if 0.2 < abs(lane - c) < P:
                    out.append((("in2", round(lane, 4)), (x + lane - c, y), y))
        return out

    def in1(self, x, y, _=None):
        base = self.row0 + math.floor((y - self.row0) / H) * H
        out = []
        for k in (-1, 0, 1):
            for off in IN1_OFFSETS:
                ly = base + k * H + off
                if 0.15 < abs(ly - y) < 0.7:
                    out.append((("in1", round(ly, 4)), (x, ly), x))
        return out


def straight_runs(leds):
    """leds: {ref: (x, y, cathode via, cathode net, anode via, anode net)} -> tracks."""
    tracks = []
    rows = defaultdict(list)
    for ref, (x, y, kv, kn, av, an) in leds.items():
        rows[round(y, 3)].append((x, kv, kn))
    for row in rows.values():
        row.sort()
        for (x1, v1, n1), (x2, v2, n2) in zip(row, row[1:]):
            if n1 == n2 and abs(x2 - x1 - P) < 1e-3:
                tracks.append(("In1.Cu", n1, [v1, v2]))
    cols = defaultdict(list)
    for ref, (x, y, kv, kn, av, an) in leds.items():
        cols[round(av[0] + av[1] * T30, 3)].append((y, av, an))
    for col in cols.values():
        col.sort()
        for (y1, v1, n1), (y2, v2, n2) in zip(col, col[1:]):
            if n1 == n2 and abs(y2 - y1 - H) < 1e-3:
                tracks.append(("In2.Cu", n1, [v1, v2]))
    return tracks


STRAIGHTEN_STEP_DEG = 30     # straightened segments must be multiples of this angle (None = any)


def _angle_ok(a, b):
    if STRAIGHTEN_STEP_DEG is None:
        return True
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
    r = ang % STRAIGHTEN_STEP_DEG
    return min(r, STRAIGHTEN_STEP_DEG - r) < 0.5


def straighten_joins(base, joins, vias):
    """Pull each join tight: keep as few of its corner points as possible (a single straight
    segment between its two vias if that is clear), checked against all vias and all other
    copper on its layer, using only segment angles that are multiples of STRAIGHTEN_STEP_DEG
    (so the board keeps to the lattice directions). Returns (new joins, number changed)."""
    out = list(joins)
    changed = 0
    for i, (layer, net, pts) in enumerate(out):
        obs = lr.Obstacles()
        for n, p in vias:
            obs.add_via(n, p)
        for j, (lyr, n, ps) in enumerate(base + out):
            if lyr == layer and not (j >= len(base) and j - len(base) == i):
                for a, b in zip(ps, ps[1:]):
                    obs.add_seg(n, a, b)
        new, k = [pts[0]], 0
        while k < len(pts) - 1:
            m = len(pts) - 1
            while m > k + 1 and not (_angle_ok(pts[k], pts[m]) and obs.clear(net, pts[k], pts[m])):
                m -= 1
            new.append(pts[m])
            k = m
        if len(new) < len(pts):
            out[i] = (layer, net, new)
            changed += 1
    return out, changed


def main(dry_run=False):
    """dry_run: compute and return the routing without touching the board file."""
    pcb = pv.PCB_FILE
    if not dry_run and pcb.with_name(f"~{pcb.name}.lck").exists():
        sys.exit(f"{pcb.name} is open in KiCad; close it first.")
    board = pcbnew.LoadBoard(str(pcb))
    for grp in list(board.Groups()):
        if grp.GetName() == GROUP:
            for item in list(grp.GetItems()):
                board.Delete(item)
            board.Delete(grp)

    mm = pcbnew.ToMM
    vias = [(t.GetNetname(), tuple(mm(t.GetPosition()))) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    via_at = {(round(p[0], 3), round(p[1], 3)): (n, p) for n, p in vias}
    stubs = [("F.Cu", t.GetNetname(), [tuple(mm(t.GetStart())), tuple(mm(t.GetEnd()))])
             for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetLayer() == pcbnew.F_Cu]
    leds = {}
    for fp in board.GetFootprints():
        if not fp.GetReference().startswith("D"):
            continue
        x, y = mm(fp.GetPosition())
        found = {}
        for num, (dx, dy) in pv.OFFSETS.items():
            n, p = via_at[(round(x + dx, 3), round(y + dy, 3))]
            found[num] = (p, n)
        leds[fp.GetReference()] = (x, y, found["1"][0], found["1"][1], found["2"][0], found["2"][1])
    x1, y1 = leds["D1"][:2]
    lat = Lattice(x1, y1)

    tracks = stubs + straight_runs(leds)
    joins = lr.route(tracks, vias, "In2.Cu", lat.in2)
    joins += lr.route(tracks + joins, vias, "In1.Cu", lat.in1)
    joins += lr.route_l(tracks + joins, vias, "B.Cu", True, lat.in1, lat.in2)
    joins, n_straight = straighten_joins(tracks, joins, vias)
    print(f"straightened {n_straight} of {len(joins)} joins")
    new = [t for t in tracks if t[0] != "F.Cu"] + joins
    if dry_run:
        return new, joins

    group = pcbnew.PCB_GROUP(board)
    group.SetName(GROUP)
    board.Add(group)
    nets = {}
    width = pcbnew.FromMM(dr.TRACK)
    segs = 0
    for layer, net, pts in new:
        nets.setdefault(net, board.FindNet(net))
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
            t.SetWidth(width)
            t.SetLayer(LAYERS[layer])
            t.SetNet(nets[net])
            board.Add(t)
            group.AddItem(t)
            segs += 1
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb), board)
    runs = len(new) - len(joins)
    print(f"{runs} straight runs + {len(joins)} joins = {segs} track segments (group '{GROUP}')")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
