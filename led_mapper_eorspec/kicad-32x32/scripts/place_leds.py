"""Place all 1024 LED footprints on the PCB, linked to the schematic symbols and with nets assigned.

Run with KiCad's Python, with the board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" scripts/place_leds.py

Existing D* footprints are removed and re-created, so this is safe to re-run.
Footprints are locked after placement. Afterwards, Tools > Update PCB from Schematic
should report no changes (footprint paths match the schematic symbol UUIDs).
"""
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charlie_map as cm          # noqa: E402
import gen_footprint as gf        # noqa: E402
import gen_schematic as gs        # noqa: E402

PCB_FILE = gs.SCH_DIR / f"{gs.PROJECT}.kicad_pcb"
ARRAY_CENTER_MM = (150.0, 100.0)   # move the whole array by changing this


def main():
    lock = PCB_FILE.with_name(f"~{PCB_FILE.name}.lck")
    if lock.exists():
        sys.exit(f"{PCB_FILE.name} is open in KiCad ({lock.name} exists); close it first.")

    board = pcbnew.LoadBoard(str(PCB_FILE))
    for fp in list(board.GetFootprints()):
        if fp.GetReference().startswith("D"):
            board.Delete(fp)

    nets = {}
    for n in range(1, cm.NUM_NETS + 1):
        name = cm.net_name(n)
        net = board.FindNet(name)
        if net is None:
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
        nets[name] = net

    template = pcbnew.FootprintLoad(str(gf.LIB_DIR), gf.FP_NAME)
    sheet_uuids = [gs.uid("sheet", name) for name, _ in gs.HALVES]
    cx, cy = ARRAY_CENTER_MM

    for led in cm.leds():
        row, col = led["row"], led["col"]
        sym_uuid = gs.uid("led", row, col)
        for half, (tag, (_, title)) in enumerate(zip(("top", "bottom"), gs.HALVES)):
            fp = pcbnew.FOOTPRINT(template)
            fp.SetFPID(pcbnew.LIB_ID(gf.LIB_NAME, gf.FP_NAME))
            fp.SetReference(led[f"ref_{tag}"])
            fp.SetValue(gs.VALUE)
            for name, value in (("Description", gs.DESCRIPTION), ("LCSC", gs.LCSC), ("Map", f"row {row} col {col}")):
                fp.SetField(name, value)
                fp.GetField(name).SetVisible(False)
                fp.GetField(name).SetLayer(pcbnew.F_Fab)
            fp.SetPath(pcbnew.KIID_PATH(f"/{sheet_uuids[half]}/{sym_uuid}"))
            fp.SetSheetname(f"/{title}/")
            fp.SetSheetfile(gs.SUB_FILE.name)
            fp.FindPadByNumber("1").SetNet(nets[led["cathode"]])
            fp.FindPadByNumber("2").SetNet(nets[led["anode"]])
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cx + led[f"x_{tag}_mm"]),
                                           pcbnew.FromMM(cy + led[f"y_{tag}_mm"])))
            fp.SetOrientationDegrees(led[f"rot_{tag}"])
            fp.SetLocked(True)
            board.Add(fp)

    board.BuildConnectivity()
    pcbnew.SaveBoard(str(PCB_FILE), board)
    print(f"placed {sum(1 for f in board.GetFootprints() if f.GetReference().startswith('D'))} LEDs "
          f"in {PCB_FILE.name}")


if __name__ == "__main__":
    main()
