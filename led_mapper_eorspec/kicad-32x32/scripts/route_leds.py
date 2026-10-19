"""Add the LED-array routing (tracks + vias from routing_geom.py) to the PCB, for both networks.

Run with KiCad's Python, with the board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" scripts/route_leds.py

All generated items go into a group named "led_routing"; re-running deletes that group's
items first, so anything routed by hand outside the group (fan-out, connector) is kept.
"""
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charlie_map as cm            # noqa: E402
import place_leds as pl             # noqa: E402
import routing_geom as rg           # noqa: E402
import lane_router as lr            # noqa: E402
import set_design_rules as dr       # noqa: E402

GROUP = "led_routing"
LAYERS = {rg.F: pcbnew.F_Cu, rg.IN1: pcbnew.In1_Cu, rg.IN2: pcbnew.In2_Cu, rg.B: pcbnew.B_Cu}


def vec(pt):
    cx, cy = pl.ARRAY_CENTER_MM
    return pcbnew.VECTOR2I(pcbnew.FromMM(cx + pt[0]), pcbnew.FromMM(cy + pt[1]))


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

    group = pcbnew.PCB_GROUP(board)
    group.SetName(GROUP)
    board.Add(group)
    nets = {n: board.FindNet(cm.net_name(n)) for n in range(1, cm.NUM_NETS + 1)}
    width = pcbnew.FromMM(dr.TRACK)

    geo = rg.build()
    tracks, vias = rg.mirrored(geo)
    tracks += lr.route_all(tracks, vias)        # lane joins: In2 first, then In1
    for layer, net, pts in tracks:
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(vec(a))
            t.SetEnd(vec(b))
            t.SetWidth(width)
            t.SetLayer(LAYERS[layer])
            t.SetNet(nets[net])
            board.Add(t)
            group.AddItem(t)
    for net, pt in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetPosition(vec(pt))
        v.SetWidth(pcbnew.FromMM(dr.VIA_DIA))
        v.SetDrill(pcbnew.FromMM(dr.VIA_DRILL))
        v.SetNet(nets[net])
        board.Add(v)
        group.AddItem(v)

    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb), board)
    n_seg = sum(len(p) - 1 for _, _, p in tracks)
    print(f"added {n_seg} track segments and {len(vias)} vias to {pcb.name} (group '{GROUP}')")


if __name__ == "__main__":
    main()
