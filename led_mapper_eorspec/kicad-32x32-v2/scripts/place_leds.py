"""Place the 1024 LEDs (and J1) on the v2 board, keeping every ref in its old row/column.

Old design (led_mapper_eorspec/rhombus): D1 top-left, refs run along the rows, 32 per row,
so Dn sits at row (n-1) div 32, column (n-1) mod 32; rows 0-15 = network1 (D1-D512),
rows 16-31 = network2 (D513-D1024); every LED rotated 180 degrees. This is checked against
the old board's coordinates before anything is placed.

Positions use the same grid and array centre as kicad-32x32 (2.09 mm pitch, rows shifted
half a pitch left going down, centre at (150, 100) mm). J1 keeps its old position and
rotation relative to the LEDs (on the back).

Footprints are linked to their schematic symbols (UUID paths) and carry the symbols'
fields, so DRC's schematic parity check passes.

Run with KiCad's Python, with the board closed in KiCad:
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" kicad-32x32-v2/scripts/place_leds.py
"""
import re
import sys
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import charlie_map as cm            # noqa: E402

NAME = "led_mapper_eorspec"
PRJ = REPO / "kicad-32x32-v2" / NAME
PCB_FILE = PRJ / f"{NAME}.kicad_pcb"
OLD_PCB = REPO / "led_mapper_eorspec" / "rhombus" / f"{NAME}.kicad_pcb"
ARRAY_CENTER_MM = (150.0, 100.0)
COLS = 32
STD_FIELDS = {"Reference", "Value", "Footprint", "Datasheet", "Description"}


def symbols(sch_file):
    """Placed symbols: {reference: (lib_id, symbol uuid, sheet path, {field: value})}."""
    text = sch_file.read_text(encoding="utf-8")
    out = {}
    for block in re.findall(r"(?ms)^\t\(symbol\r?\n.*?^\t\)", text):
        lib_id = re.search(r'\(lib_id "([^"]+)"\)', block).group(1)
        uuid = re.search(r'^\t\t\(uuid "([^"]+)"\)', block, re.M).group(1)
        fields = dict(re.findall(r'^\t\t\(property "([^"]+)" "([^"]*)"', block, re.M))
        for path, ref in re.findall(r'\(path "([^"]+)"\s*\(reference "([^"]+)"\)', block):
            out[ref] = (lib_id, uuid, path, fields)
    return out


def row_col(ref):
    return divmod(int(ref[1:]) - 1, COLS)


def check_against_old_board():
    old = pcbnew.LoadBoard(str(OLD_PCB))
    leds = {f.GetReference(): pcbnew.ToMM(f.GetPosition()) for f in old.GetFootprints()
            if f.GetReference().startswith("D")}
    x0, y0 = leds["D1"]
    bad = []
    for ref, (x, y) in leds.items():
        r = round((y - y0) / cm.ROW_H)
        c = round((x - x0 + r * cm.PITCH / 2) / cm.PITCH)
        if (r, c) != row_col(ref):
            bad.append(ref)
    if bad:
        sys.exit(f"old board does not follow the row/column rule for {len(bad)} LEDs, e.g. {bad[:5]}")
    old_j1 = old.FindFootprintByReference("J1")
    j1_rel = tuple(a - b for a, b in zip(pcbnew.ToMM(old_j1.GetPosition()), leds["D1"]))
    return len(leds), j1_rel, old_j1.GetOrientationDegrees()


def main():
    if PCB_FILE.with_name(f"~{PCB_FILE.name}.lck").exists():
        sys.exit(f"{PCB_FILE.name} is open in KiCad; close it first.")
    n_old, j1_rel, j1_rot = check_against_old_board()

    syms = {}
    syms.update(symbols(PRJ / f"{NAME}.kicad_sch"))
    syms.update(symbols(PRJ / "single_net.kicad_sch"))
    sheet_names = {"0336ac2d-1518-434b-98ce-7b750e20605b": "network1",
                   "76ddcdbd-de4c-41a8-b473-9f82d139a399": "network2"}

    # pin nets from KiCad's own netlist export of the copied schematic
    import subprocess, tempfile
    net_file = Path(tempfile.gettempdir()) / "v2_place.net"
    subprocess.run([r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe", "sch", "export", "netlist",
                    "--format", "kicadsexpr", "-o", str(net_file), str(PRJ / f"{NAME}.kicad_sch")],
                   check=True, capture_output=True)
    t = net_file.read_text(encoding="utf-8")
    pin_net = {}
    for blk in t[t.index("(nets"):].split("(net\n")[1:]:
        name = re.search(r'\(name "([^"]+)"\)', blk).group(1)
        for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk):
            pin_net[(ref, pin)] = name

    board = pcbnew.LoadBoard(str(PCB_FILE))
    for fp in list(board.GetFootprints()):
        board.Delete(fp)
    nets = {}
    for name in sorted(set(pin_net.values())):
        net = board.FindNet(name)
        if net is None:
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
        nets[name] = net

    cx, cy = ARRAY_CENTER_MM
    d1 = None
    placed = 0
    for ref, (lib_id, uuid, path, fields) in sorted(syms.items(), key=lambda s: (s[0][0], int(s[0][1:]))):
        lib, name = fields["Footprint"].split(":")
        fp = pcbnew.FootprintLoad(str(PRJ / f"{lib}.pretty"), name)
        board.Add(fp)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(fields.get("Value", ""))
        for k, v in fields.items():
            if k in ("Reference", "Value", "Footprint"):
                continue
            fp.SetField(k, v)
            fp.GetField(k).SetVisible(False)
            fp.GetField(k).SetLayer(pcbnew.F_Fab)
        sheet = path.split("/")[2] if path.count("/") >= 2 else ""
        fp.SetPath(pcbnew.KIID_PATH(f"/{sheet}/{uuid}" if sheet else f"/{uuid}"))
        fp.SetSheetname(f"/{sheet_names[sheet]}/" if sheet else "/")
        fp.SetSheetfile("single_net.kicad_sch" if sheet else f"{NAME}.kicad_sch")
        for pad in fp.Pads():
            net = pin_net.get((ref, pad.GetNumber()))
            if net:
                pad.SetNet(nets[net])
        if ref.startswith("D"):
            r, c = row_col(ref)
            x, y = cm.board_xy(r, c)
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(cx + x), pcbnew.FromMM(cy + y)))
            fp.SetOrientationDegrees(180)
            fp.SetLocked(True)
            if ref == "D1":
                d1 = (cx + x, cy + y)
        placed += 1

    j1 = board.FindFootprintByReference("J1")
    pos = pcbnew.VECTOR2I(pcbnew.FromMM(d1[0] + j1_rel[0]), pcbnew.FromMM(d1[1] + j1_rel[1]))
    j1.SetPosition(pos)
    j1.Flip(pos, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    j1.SetOrientationDegrees(j1_rot)

    board.BuildConnectivity()
    pcbnew.SaveBoard(str(PCB_FILE), board)
    print(f"checked {n_old} old LED positions; placed {placed} footprints; D1 at {d1}, "
          f"J1 at ({d1[0] + j1_rel[0]:.3f}, {d1[1] + j1_rel[1]:.3f}) rot {j1_rot}")


if __name__ == "__main__":
    main()
