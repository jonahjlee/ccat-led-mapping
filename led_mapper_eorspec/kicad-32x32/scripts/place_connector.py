"""Place the 24-pin connector J1 on the back, along the array's lower-right edge.

The rhombus has obtuse (120 degree) corners at the top-left and bottom-right; J1 sits
along the slanted right edge next to the bottom-right one, its lower end level with the
last row. Along that stretch the row ends carry P01-P08 and P17-P24, and P09-P15 come out
along the bottom edge right next to the corner. The rotation is chosen so pin 1 is at the
upper end. Pin nets come from connector_map.csv (chosen by fanout.py; pin n = Pn before that).

Run with KiCad's Python, with the board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" scripts/place_connector.py
"""
import math
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charlie_map as cm            # noqa: E402
import gen_footprint as gf          # noqa: E402
import gen_schematic as gs          # noqa: E402
import place_leds as pl             # noqa: E402
import routing_geom as rg           # noqa: E402

FP_NAME = gs.CONN_FOOTPRINT.split(":")[1]
GAP = 2.5           # mm from the edge vias' copper to the nearest pad tip (room for fan-out)
PAD_REACH = 6.02    # mm from connector centre to the outer pad tips (perpendicular)
BODY_HALF = 17.9    # mm, half the footprint length along its axis


def main():
    pcb = pl.PCB_FILE
    if pcb.with_name(f"~{pcb.name}.lck").exists():
        sys.exit(f"{pcb.name} is open in KiCad; close it first.")
    board = pcbnew.LoadBoard(str(pcb))
    for fp in list(board.GetFootprints()):
        if fp.GetReference() == gs.CONN_REF:
            board.Delete(fp)

    # edge geometry (mm relative to the array centre): bottom network, last row's right-end via
    down = (-math.sin(math.radians(30)), math.cos(math.radians(30)))   # along the edge, downwards
    out = (down[1], -down[0])                                           # outward normal (right)
    ex, ey = rg.hvia(15, 15, +1)
    off = 0.225 + GAP + PAD_REACH
    cx = ex + out[0] * off - down[0] * BODY_HALF
    cy = ey + out[1] * off - down[1] * BODY_HALF
    acx, acy = pl.ARRAY_CENTER_MM
    centre = pcbnew.VECTOR2I(pcbnew.FromMM(acx + cx), pcbnew.FromMM(acy + cy))

    fp = pcbnew.FootprintLoad(str(gf.LIB_DIR), FP_NAME)
    board.Add(fp)                                     # flipping needs the board as parent
    fp.SetFPID(pcbnew.LIB_ID(gf.LIB_NAME, FP_NAME))
    fp.SetReference(gs.CONN_REF)
    fp.SetValue("Conn_02x12")
    fp.SetField("Description", gs.CONN_DESC)
    pin_net = gs.conn_map()
    fp.SetPath(pcbnew.KIID_PATH(f"/{gs.uid('conn', gs.CONN_REF)}"))
    fp.SetSheetname("/")
    fp.SetSheetfile(gs.ROOT_FILE.name)
    for n in range(1, 25):
        fp.FindPadByNumber(str(n)).SetNet(board.FindNet(cm.net_name(pin_net[n])))
    fp.SetPosition(centre)
    fp.Flip(centre, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)

    best = None
    for rot in range(-180, 180, 30):
        fp.SetOrientationDegrees(rot)
        p1 = pcbnew.ToMM(fp.FindPadByNumber("1").GetPosition())
        p12 = pcbnew.ToMM(fp.FindPadByNumber("12").GetPosition())
        axis = ((p12[0] - p1[0]) / 27.94, (p12[1] - p1[1]) / 27.94)
        rel = (p1[0] - acx - cx, p1[1] - acy - cy)
        aligned = axis[0] * down[0] + axis[1] * down[1]          # 1 = pins 1->12 run down the edge
        inner = rel[0] * out[0] + rel[1] * out[1]                # < 0 = pin 1 column faces the array
        score = (round(aligned, 3), -inner)
        if best is None or score > best[0]:
            best = (score, rot)
    rot = best[1]
    fp.SetOrientationDegrees(rot)
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb), board)
    print(f"placed {gs.CONN_REF} on {fp.GetLayerName()} at ({acx + cx:.3f}, {acy + cy:.3f}) mm, "
          f"rotation {rot} deg (alignment score {best[0]})")


if __name__ == "__main__":
    main()
