"""Give both pads of every LED their own via (option B, "diagonal"), with an F.Cu stub to each.

LEDs are rotated 180 degrees, so the cathode (pad 1, a row net) is on the right and the
anode (pad 2, a column net) on the left. Relative to each LED centre:
    cathode via  (+3P/8, -H/4) = (+0.784, -0.452) mm   up and to the right
    anode via    (-3P/8, +H/4) = (-0.784, +0.452) mm   down and to the left
with P = 2.09 mm (LED pitch) and H = sqrt(3)/2 * P (row height). These offsets put every
cathode via exactly midway between two anode column lines (60-degree In2 tracks through the
anode vias) and every anode via exactly midway between two cathode row lines (horizontal In1
tracks through the cathode vias). Both stubs of an LED are the same length (0.74 mm).

Items go into the group "led_vias"; re-running replaces only that group.

Run with KiCad's Python, with the board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" kicad-32x32-v2/scripts/place_vias.py
"""
import math
import sys
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import set_design_rules as dr       # noqa: E402

NAME = "led_mapper_eorspec"
PCB_FILE = REPO / "kicad-32x32-v2" / NAME / f"{NAME}.kicad_pcb"
GROUP = "led_vias"
P = 2.09
H = P * math.sqrt(3) / 2
OFFSETS = {"1": (+3 * P / 8, -H / 4),     # cathode
           "2": (-3 * P / 8, +H / 4)}     # anode


def main():
    if PCB_FILE.with_name(f"~{PCB_FILE.name}.lck").exists():
        sys.exit(f"{PCB_FILE.name} is open in KiCad; close it first.")
    board = pcbnew.LoadBoard(str(PCB_FILE))
    for grp in list(board.Groups()):
        if grp.GetName() == GROUP:
            for item in list(grp.GetItems()):
                board.Delete(item)
            board.Delete(grp)
    group = pcbnew.PCB_GROUP(board)
    group.SetName(GROUP)
    board.Add(group)

    n = 0
    for fp in board.GetFootprints():
        if not fp.GetReference().startswith("D"):
            continue
        centre = fp.GetPosition()
        for num, (dx, dy) in OFFSETS.items():
            pad = fp.FindPadByNumber(num)
            # sanity: cathode on the right, anode on the left (LEDs at 180 degrees)
            assert (pad.GetPosition().x > centre.x) == (num == "1"), fp.GetReference()
            at = pcbnew.VECTOR2I(centre.x + pcbnew.FromMM(dx), centre.y + pcbnew.FromMM(dy))
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetPosition(at)
            via.SetWidth(pcbnew.FromMM(dr.VIA_DIA))
            via.SetDrill(pcbnew.FromMM(dr.VIA_DRILL))
            via.SetNet(pad.GetNet())
            board.Add(via)
            group.AddItem(via)
            stub = pcbnew.PCB_TRACK(board)
            stub.SetStart(pad.GetPosition())
            stub.SetEnd(at)
            stub.SetWidth(pcbnew.FromMM(dr.TRACK))
            stub.SetLayer(pcbnew.F_Cu)
            stub.SetNet(pad.GetNet())
            board.Add(stub)
            group.AddItem(stub)
            n += 1

    board.BuildConnectivity()
    pcbnew.SaveBoard(str(PCB_FILE), board)
    print(f"added {n} vias and {n} stubs (group '{GROUP}')")


if __name__ == "__main__":
    main()
