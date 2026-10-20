"""Put J1 where it is on the v1 board and draw the v2 board outline from the edge DXF.

  - J1: same position, side and rotation as J1 on kicad-32x32's board (read from that file),
    which is valid because both boards use the same LED grid and array centre. Its pin nets
    are left as the schematic defines them.
  - Outline: led_mapper_eorspec/edge_v4.dxf (copy of data/edge_v4.dxf), placed exactly as on
    the v1 board: DXF origin 2 mm left of and 2 mm above the upper-left LED centre, DXF y axis
    flipped to KiCad's (y down). Lines go into the group "outline" on Edge.Cuts.

Run with KiCad's Python, with the v2 board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" kicad-32x32-v2/scripts/place_connector_outline.py
"""
import sys
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[2]
NAME = "led_mapper_eorspec"
PCB_FILE = REPO / "kicad-32x32-v2" / NAME / f"{NAME}.kicad_pcb"
V1_PCB = REPO / "kicad-32x32" / "eorspec_rhombus" / "eorspec_rhombus.kicad_pcb"
DXF = REPO / "kicad-32x32-v2" / NAME / "edge_v4.dxf"
GROUP = "outline"
EDGE_WIDTH = 0.1
ORIGIN_FROM_D1 = (-2.0, -2.0)      # DXF origin relative to the upper-left LED (D1) centre


def dxf_lines(path):
    """LINE entities of an ASCII DXF as ((x1, y1), (x2, y2)) in DXF units (mm)."""
    toks = [line.strip() for line in open(path, encoding="utf-8", errors="replace")]
    pairs = list(zip(toks[0::2], toks[1::2]))
    out, i = [], 0
    while i < len(pairs):
        if pairs[i] == ("0", "LINE"):
            d, i = {}, i + 1
            while i < len(pairs) and pairs[i][0] != "0":
                d[pairs[i][0]] = pairs[i][1]
                i += 1
            out.append(((float(d["10"]), float(d["20"])), (float(d["11"]), float(d["21"]))))
        else:
            i += 1
    return out


def main():
    if PCB_FILE.with_name(f"~{PCB_FILE.name}.lck").exists():
        sys.exit(f"{PCB_FILE.name} is open in KiCad; close it first.")
    v1 = pcbnew.LoadBoard(str(V1_PCB))
    j1_v1 = v1.FindFootprintByReference("J1")
    pos, rot, back = j1_v1.GetPosition(), j1_v1.GetOrientationDegrees(), j1_v1.IsFlipped()

    board = pcbnew.LoadBoard(str(PCB_FILE))
    j1 = board.FindFootprintByReference("J1")
    if j1.IsFlipped() != back:
        j1.Flip(j1.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    j1.SetPosition(pos)
    j1.SetOrientationDegrees(rot)

    for grp in list(board.Groups()):
        if grp.GetName() == GROUP:
            for item in list(grp.GetItems()):
                board.Delete(item)
            board.Delete(grp)
    d1 = pcbnew.ToMM(board.FindFootprintByReference("D1").GetPosition())
    ox, oy = d1[0] + ORIGIN_FROM_D1[0], d1[1] + ORIGIN_FROM_D1[1]
    group = pcbnew.PCB_GROUP(board)
    group.SetName(GROUP)
    board.Add(group)
    lines = dxf_lines(DXF)
    for (x1, y1), (x2, y2) in lines:
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(EDGE_WIDTH))
        s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ox + x1), pcbnew.FromMM(oy - y1)))
        s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(ox + x2), pcbnew.FromMM(oy - y2)))
        board.Add(s)
        group.AddItem(s)

    board.BuildConnectivity()
    pcbnew.SaveBoard(str(PCB_FILE), board)
    print(f"J1 at {[round(v, 4) for v in pcbnew.ToMM(pos)]} rot {rot} ({'back' if back else 'front'}); "
          f"outline: {len(lines)} lines from {DXF.name}, origin ({ox:.4f}, {oy:.4f})")


if __name__ == "__main__":
    main()
