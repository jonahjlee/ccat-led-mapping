"""Fan-out for v2: connect each J1 pin to its net, keeping the 850 board's pinout (pin n = Pn).

Each J1 pad gets a through via in the strip between the two pad columns, next to the pad's
inner end, joined to the pad by a short B.Cu stub. That leaves two tidy rows of vias down
the middle of the connector and lets every net reach its pin on whichever layer is free.
(The vias are beside the pads, not in them: no solder wicking, no via-in-pad cost.)

Each net is routed from its nearest vias in the array to its pin via along the P/8 lattice
(0/60/120-degree segments, bend penalty; route_structured.lattice_path), trying In1, In2 and
B.Cu (B.Cu with a length penalty, so the pin vias get used) and keeping the shortest;
all tracks clear the board edge, and B.Cu tracks clear J1's pads. Nets are routed in order
of distance (closest first). Everything goes into the group "fanout".

Run with KiCad's Python, with the v2 board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" kicad-32x32-v2/scripts/fanout.py
"""
import math
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_structured as rs      # noqa: E402  (sets up the import path for the shared modules)
import lane_router as lr            # noqa: E402
import place_vias as pv             # noqa: E402
import set_design_rules as dr       # noqa: E402

GROUP = "fanout"
VIA_FROM_AXIS = 0.6       # mm from the connector's centre line to each pin via
SEARCH_RADIUS = 30.0      # mm: array vias considered as start points for a net
LAYERS = ("In1.Cu", "In2.Cu", "B.Cu")
LAYER_PENALTY = {"In1.Cu": 0.0, "In2.Cu": 0.0, "B.Cu": 8.0}   # mm: keep pin vias in use
EDGE_CLEARANCE = dr.BOARD_MINIMUMS["min_copper_edge_clearance"]


def _in_poly(pt, poly):
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


class WithPads:
    """Obstacle check that also keeps tracks clear of the board edge (all layers) and, on
    B.Cu, of other nets' J1 pads (their real rectangular outlines)."""

    def __init__(self, obs, pads, edges):
        self.obs, self.pads, self.edges = obs, pads, edges   # pads: [(net, [corner points])]

    def clear(self, net, a, b):
        if not self.obs.clear(net, a, b):
            return False
        for e0, e1 in self.edges:
            if lr._seg_seg(a, b, e0, e1) < EDGE_CLEARANCE + lr.HALF_W:
                return False
        for n, poly in self.pads:
            if n == net:
                continue
            if _in_poly(a, poly) or _in_poly(b, poly):
                return False
            for q0, q1 in zip(poly, poly[1:] + poly[:1]):
                if lr._seg_seg(a, b, q0, q1) < lr.HALF_W + lr.CLR:
                    return False
        return True


def main():
    pcb = pv.PCB_FILE
    if pcb.with_name(f"~{pcb.name}.lck").exists():
        sys.exit(f"{pcb.name} is open in KiCad; close it first.")
    board = pcbnew.LoadBoard(str(pcb))
    for grp in list(board.Groups()):
        if grp.GetName() == GROUP:
            for item in list(grp.GetItems()):
                board.Delete(item)
            board.Delete(grp)
    mm = pcbnew.ToMM

    j1 = board.FindFootprintByReference("J1")
    centre = mm(j1.GetPosition())
    raw = {int(p.GetNumber()): (p.GetNetname(), tuple(mm(p.GetPosition())), p.GetSize(pcbnew.B_Cu))
           for p in j1.Pads()}
    p1, p12 = raw[1][1], raw[12][1]
    axis = ((p12[0] - p1[0]) / math.dist(p1, p12), (p12[1] - p1[1]) / math.dist(p1, p12))
    u = (-axis[1], axis[0])                              # pads lie across the connector axis
    pads = {k: (net, c, u, max(mm(sz.x), mm(sz.y)) / 2, min(mm(sz.x), mm(sz.y)) / 2)
            for k, (net, c, sz) in raw.items()}
    line_pt = ((pads[1][1][0] + pads[13][1][0]) / 2, (pads[1][1][1] + pads[13][1][1]) / 2)

    pin_vias, stubs = {}, []
    for k, (net, c, u, hl, hw) in pads.items():
        # signed distance of the pad centre from the centre line, along the pad axis
        off = (c[0] - line_pt[0]) * u[0] + (c[1] - line_pt[1]) * u[1]
        side = 1 if off > 0 else -1
        v = (c[0] - u[0] * (abs(off) - VIA_FROM_AXIS) * side, c[1] - u[1] * (abs(off) - VIA_FROM_AXIS) * side)
        pin_vias[k] = (net, v)
        stubs.append(("B.Cu", net, [c, v]))

    vias, _, leds, grid, lat = rs.load(board)
    tracks = [(t.GetLayerName(), t.GetNetname(), [tuple(mm(t.GetStart())), tuple(mm(t.GetEnd()))])
              for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    all_vias = vias + [(n, v) for n, v in pin_vias.values()]
    pad_list = []
    for p in j1.Pads():
        o = p.GetEffectivePolygon(pcbnew.B_Cu, pcbnew.ERROR_INSIDE).Outline(0)
        pad_list.append((p.GetNetname(), [tuple(mm(o.CPoint(i))) for i in range(o.PointCount())]))
    edges = [(tuple(mm(d.GetStart())), tuple(mm(d.GetEnd()))) for d in board.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts]

    order = sorted(pin_vias, key=lambda k: min(
        math.dist(p, pin_vias[k][1]) for n, p in vias if n == pin_vias[k][0]))
    routed, new = {}, list(stubs)
    for k in order:
        net, target = pin_vias[k]
        srcs = [p for n, p in vias if n == net and math.dist(p, target) < SEARCH_RADIUS]
        best = None
        for layer in LAYERS:
            obs = rs.obstacles(layer, tracks + new, all_vias)
            chk = WithPads(obs, pad_list if layer == "B.Cu" else [], edges)
            path = rs.lattice_path(lat, chk, net, srcs, [target])
            if not path:
                continue
            if math.dist(path[-1], target) > 1e-6:
                if not chk.clear(net, path[-1], target):
                    continue
                path = path + [target]
            length = sum(math.dist(a, b) for a, b in zip(path, path[1:])) + 0.5 * len(path) + LAYER_PENALTY[layer]
            if best is None or length < best[0]:
                best = (length, layer, path)
        if best:
            path = best[2]
            if best[1] == "B.Cu":
                # on B.Cu the pad is reached directly: drop the pin-via stub and finish with one
                # straight segment to the pad centre from the earliest point that sees it clearly
                pad_c = pads[k][1]
                stub = ("B.Cu", net, [pad_c, target])
                new = [t for t in new if t != stub]
                chk = WithPads(rs.obstacles("B.Cu", tracks + new, all_vias), pad_list, edges)
                for i in range(len(path)):
                    if chk.clear(net, path[i], pad_c):
                        path = path[:i + 1] + [pad_c]
                        break
                # stop (or extend) the run before the last corner where it meets the pad's long
                # centre line, then go along the centre line into the pad centre (no kink)
                if len(path) >= 3:
                    p, q, u = path[-3], path[-2], pads[k][2]
                    d = (q[0] - p[0], q[1] - p[1])
                    den = d[0] * u[1] - d[1] * u[0]
                    if abs(den) > 1e-9:
                        t = ((pad_c[0] - p[0]) * u[1] - (pad_c[1] - p[1]) * u[0]) / den
                        x = (p[0] + d[0] * t, p[1] + d[1] * t)
                        if t > 0 and chk.clear(net, p, x) and chk.clear(net, x, pad_c):
                            path = path[:-2] + [x, pad_c]
            new.append((best[1], net, path))
            routed[k] = best[1]
        else:
            print(f"  pin {k} ({net}): no route")

    group = pcbnew.PCB_GROUP(board)
    group.SetName(GROUP)
    board.Add(group)
    nets = {}
    for k, (net, v) in pin_vias.items():
        if routed.get(k) == "B.Cu":
            continue                          # track arrives on B.Cu: the pin via would dangle
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(v[0]), pcbnew.FromMM(v[1])))
        via.SetWidth(pcbnew.FromMM(dr.VIA_DIA))
        via.SetDrill(pcbnew.FromMM(dr.VIA_DRILL))
        via.SetNet(nets.setdefault(net, board.FindNet(net)))
        board.Add(via)
        group.AddItem(via)
    for layer, net, pts in new:
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
            t.SetWidth(pcbnew.FromMM(dr.TRACK))
            t.SetLayer(rs.rl.LAYERS[layer])
            t.SetNet(nets.setdefault(net, board.FindNet(net)))
            board.Add(t)
            group.AddItem(t)
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb), board)
    from collections import Counter
    print(f"fan-out: {len(routed)}/24 pins routed {dict(Counter(routed.values()))}; "
          f"{sum(1 for k in pin_vias if routed.get(k) != 'B.Cu')} pin vias added")


if __name__ == "__main__":
    main()
