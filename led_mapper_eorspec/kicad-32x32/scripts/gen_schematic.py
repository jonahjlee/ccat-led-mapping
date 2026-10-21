"""Generate the KiCad schematic: a root sheet with two instances of one charlieplexed network.

  eorspec_rhombus.kicad_sch   root: two sheet symbols (Top, Bottom) + global labels P01-P24
  charlie_network.kicad_sch   one network: 16x16 pair cells, drawn on the same grid as the board

Each pair cell is drawn as two antiparallel LEDs (upper = left LED on the board,
lower = right LED) joined at both ends, with a hierarchical label per end:
left label = h net, right label = v net (see charlie_map.py).

UUIDs are derived from names, so regenerating gives stable diffs.
Close the schematic in KiCad before running.
"""
import uuid
from pathlib import Path

import charlie_map as cm

PROJECT = "eorspec_rhombus"
SCH_DIR = Path(__file__).resolve().parent.parent / "kicad-32x32" / PROJECT
ROOT_FILE = SCH_DIR / f"{PROJECT}.kicad_sch"
SUB_FILE = SCH_DIR / "charlie_network.kicad_sch"
ROOT_UUID = "54be569c-d5c1-4f2e-8d65-128bec4a2884"  # keep the project's existing root uuid
LIB_SYM = Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols\Device.kicad_sym")

FOOTPRINT = "eorspec:LED_0201_XL-0201SURC"
VALUE = "XL-0201SURC"
LCSC = "C3646923"
DESCRIPTION = "Red LED, 0201 (XINGLIGHT XL-0201SURC)"

CONN_LIB = LIB_SYM.with_name("Connector_Generic.kicad_sym")
CONN_SYMBOL = "Conn_02x12_Top_Bottom"
CONN_FOOTPRINT = "eorspec:PinSocket_2x12_P2.54mm_Vertical_SMD_custom"
CONN_REF = "J1"
CONN_AT = (228.6, 78.74)       # root sheet position
CONN_MAP_CSV = cm.CSV_PATH.with_name("connector_map.csv")   # pin -> net, written by fanout.py
CONN_DESC = "24-pin socket to the Arduino Mega (pin map: kicad-32x32/connector_map.csv)"


def conn_map() -> dict:
    """{pin: net number}; pin n = Pn until fanout.py has chosen the mapping."""
    import csv
    if not CONN_MAP_CSV.exists():
        return {n: n for n in range(1, 25)}
    with open(CONN_MAP_CSV, newline="") as f:
        return {int(r["pin"]): int(r["net"][1:]) for r in csv.DictReader(f)}

HALVES = [("Top", "Network Top (D1-D512)"), ("Bottom", "Network Bottom (D513-D1024)")]

# Sub-sheet layout (mm, schematic y points down)
CELL_DX, CELL_DY = 27.94, 12.7
X0, Y0 = 50.8, 50.8
LED_GAP = 5.08    # vertical distance between the two LEDs of a cell
PIN = 3.81        # LED pin offset from symbol centre
LABEL_STUB = 2.54


def uid(*parts) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "eorspec_rhombus/" + "/".join(map(str, parts))))


def fmt(v: float) -> str:
    return f"{round(v, 4):g}"


def font(size=1.27, extra=""):
    return f"(effects (font (size {fmt(size)} {fmt(size)})){extra})"


# ---------------------------------------------------------------- primitives

def wire(x1, y1, x2, y2, key):
    return (f"\t(wire (pts (xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)}))\n"
            f"\t\t(stroke (width 0) (type default)) (uuid \"{uid('wire', key)}\"))\n")


def junction(x, y, key):
    return f"\t(junction (at {fmt(x)} {fmt(y)}) (diameter 0) (color 0 0 0 0) (uuid \"{uid('junc', key)}\"))\n"


def hier_label(name, x, y, facing_left, key):
    angle, just = (180, "right") if facing_left else (0, "left")
    return (f"\t(hierarchical_label \"{name}\" (shape bidirectional) (at {fmt(x)} {fmt(y)} {angle})\n"
            f"\t\t{font(1.27, f' (justify {just})')} (uuid \"{uid('hlabel', key)}\"))\n")


def text(s, x, y, size=1.27, key=None, just="left bottom"):
    return (f"\t(text \"{s}\" (exclude_from_sim no) (at {fmt(x)} {fmt(y)} 0)\n"
            f"\t\t{font(size, f' (justify {just})')} (uuid \"{uid('text', key or s)}\"))\n")


def line(x1, y1, x2, y2, key):
    return (f"\t(polyline (pts (xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)}))\n"
            f"\t\t(stroke (width 0.3) (type dash)) (fill (type none)) (uuid \"{uid('line', key)}\"))\n")


def prop(name, value, x, y, hide=True, size=1.27):
    h = " (hide yes)" if hide else ""
    return (f"\t\t(property \"{name}\" \"{value}\" (at {fmt(x)} {fmt(y)} 0){h}\n"
            f"\t\t\t(show_name no) (do_not_autoplace no) {font(size)})\n")


def led_symbol(x, y, angle, row, col, sheet_uuids):
    refs = [cm.ref(half, row, col) for half in range(2)]
    ref_y = y - 2.54 if angle == 0 else y + 2.54
    out = (f"\t(symbol (lib_id \"Device:LED\") (at {fmt(x)} {fmt(y)} {angle}) (unit 1) (body_style 1)\n"
           f"\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (in_pos_files yes) (dnp no)\n"
           f"\t\t(uuid \"{uid('led', row, col)}\")\n")
    out += prop("Reference", refs[0], x, ref_y, hide=False, size=1.0)
    out += prop("Value", VALUE, x, y)
    out += prop("Footprint", FOOTPRINT, x, y)
    out += prop("Datasheet", "", x, y)
    out += prop("Description", DESCRIPTION, x, y)
    out += prop("LCSC", LCSC, x, y)
    out += prop("Map", f"row {row} col {col}", x, y)
    out += f"\t\t(pin \"1\" (uuid \"{uid('pin1', row, col)}\"))\n"
    out += f"\t\t(pin \"2\" (uuid \"{uid('pin2', row, col)}\"))\n"
    out += f"\t\t(instances (project \"{PROJECT}\"\n"
    for su, r in zip(sheet_uuids, refs):
        out += f"\t\t\t(path \"/{ROOT_UUID}/{su}\" (reference \"{r}\") (unit 1))\n"
    out += "\t\t))\n\t)\n"
    return out


def lib_symbol(lib_file=LIB_SYM, name="LED", lib="Device") -> str:
    """Copy a symbol definition out of a KiCad library, renamed with its lib prefix."""
    lines = lib_file.read_text(encoding="utf-8").splitlines()
    start = lines.index(f'\t(symbol "{name}"')
    end = lines.index("\t)", start)
    block = "\n".join(lines[start:end + 1])
    return block.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


def header(file_uuid, paper):
    return ("(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
            f"\t(uuid \"{file_uuid}\")\n\t(paper \"{paper}\")\n")


# ---------------------------------------------------------------- sub-sheet

def build_subsheet(sheet_uuids) -> str:
    out = header(uid("subsheet"), "A2")
    out += "\t(lib_symbols\n" + lib_symbol() + "\n\t)\n"

    out += text("One charlieplexed network: 16 x 16 pair cells (= 16 rows x 32 LEDs). "
                "Drawn on the same row/column grid as the board.", X0 - 25.4, Y0 - 30.48, 2.5, "title")
    out += text("Each cell = left LED (upper symbol, K=left net) + right LED (lower symbol, K=right net). "
                "Groups: A=P01-P08, B=P09-P16, C=P17-P24.  Mapping source: scripts/charlie_map.py, kicad-32x32/led_map.csv",
                X0 - 25.4, Y0 - 25.4, 1.5, "subtitle")

    for c in range(cm.CELL_COLS):
        out += text(f"cell col {c}", X0 + c * CELL_DX - 5.08, Y0 - 7.62, 1.27, f"colhdr{c}")
    for r in range(cm.CELL_ROWS):
        out += text(f"row {r}", X0 - 22.86, Y0 + r * CELL_DY + LED_GAP / 2 + 0.6, 1.27, f"rowhdr{r}")

    for r in range(cm.CELL_ROWS):
        for c in range(cm.CELL_COLS):
            h, v, _ = cm.cell_nets(r, c)
            x, y = X0 + c * CELL_DX, Y0 + r * CELL_DY
            ym = y + LED_GAP / 2
            out += led_symbol(x, y, 0, r, 2 * c, sheet_uuids)
            out += led_symbol(x, y + LED_GAP, 180, r, 2 * c + 1, sheet_uuids)
            for side, net in ((-1, h), (1, v)):
                px = x + side * PIN
                k = (r, c, side)
                out += wire(px, y, px, ym, k + ("a",))
                out += wire(px, ym, px, y + LED_GAP, k + ("b",))
                out += wire(px, ym, px + side * LABEL_STUB, ym, k + ("s",))
                out += junction(px, ym, k)
                out += hier_label(cm.net_name(net), px + side * LABEL_STUB, ym, side < 0, k)

    # quadrant dividers
    xm = X0 + 7.5 * CELL_DX
    ym = Y0 + 8 * CELL_DY - (CELL_DY - LED_GAP) / 2
    out += line(xm, Y0 - 5.08, xm, Y0 + 16 * CELL_DY, "vdiv")
    out += line(X0 - 15.24, ym, X0 + 16 * CELL_DX - 12.7, ym, "hdiv")
    return out + "\t(embedded_fonts no)\n)\n"


# ---------------------------------------------------------------- root sheet

def connector() -> str:
    """J1: 2x12 socket on the root sheet, each pin wired to its net's global label (conn_map)."""
    x, y = CONN_AT
    out = (f"\t(symbol (lib_id \"Connector_Generic:{CONN_SYMBOL}\") (at {fmt(x)} {fmt(y)} 0) (unit 1) (body_style 1)\n"
           f"\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (in_pos_files yes) (dnp no)\n"
           f"\t\t(uuid \"{uid('conn', CONN_REF)}\")\n")
    out += prop("Reference", CONN_REF, x + 1.27, y - 15.24, hide=False)
    out += prop("Value", "Conn_02x12", x + 1.27, y + 20.32, hide=False)
    out += prop("Footprint", CONN_FOOTPRINT, x, y)
    out += prop("Datasheet", "", x, y)
    out += prop("Description", CONN_DESC, x, y)
    pin_net = conn_map()
    for n in range(1, 25):
        out += f"\t\t(pin \"{n}\" (uuid \"{uid('connpin', n)}\"))\n"
    out += f"\t\t(instances (project \"{PROJECT}\" (path \"/{ROOT_UUID}\" (reference \"{CONN_REF}\") (unit 1))))\n\t)\n"
    for n in range(1, 25):
        left = n <= 12
        py = y - 12.7 + 2.54 * ((n - 1) % 12)
        px = x - 5.08 if left else x + 7.62
        lx = px - 5.08 if left else px + 5.08
        angle, just = (180, "right") if left else (0, "left")
        out += wire(px, py, lx, py, ("conn", n))
        out += (f"\t(global_label \"{cm.net_name(pin_net[n])}\" (shape bidirectional) (at {fmt(lx)} {fmt(py)} {angle})\n"
                f"\t\t(fields_autoplaced yes) {font(1.27, f' (justify {just})')}\n"
                f"\t\t(uuid \"{uid('connlabel', n)}\")\n"
                f"\t\t(property \"Intersheetrefs\" \"${{INTERSHEET_REFS}}\" (at {fmt(lx)} {fmt(py)} 0)\n"
                f"\t\t\t{font(1.27, f' (justify {just}) (hide yes)')}))\n")
    return out


def build_root(sheet_uuids) -> str:
    out = header(ROOT_UUID, "A4")
    out += "\t(lib_symbols\n" + lib_symbol(CONN_LIB, CONN_SYMBOL, "Connector_Generic") + "\n\t)\n"
    out += connector()
    out += text("Two charlieplexed networks driven in parallel by the same 24 lines P01-P24.", 25.4, 30.48, 1.5, "rootnote")
    w, hgt, pitch = 38.1, 66.04, 2.54
    for n, ((name, title), su) in enumerate(zip(HALVES, sheet_uuids)):
        sx, sy = 38.1 + n * 101.6, 45.72
        out += (f"\t(sheet (at {fmt(sx)} {fmt(sy)}) (size {fmt(w)} {fmt(hgt)})\n"
                f"\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n"
                f"\t\t(stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000))\n"
                f"\t\t(uuid \"{su}\")\n"
                f"\t\t(property \"Sheetname\" \"{title}\" (at {fmt(sx)} {fmt(sy - 0.7)} 0)\n"
                f"\t\t\t{font(1.27, ' (justify left bottom)')})\n"
                f"\t\t(property \"Sheetfile\" \"{SUB_FILE.name}\" (at {fmt(sx)} {fmt(sy + hgt + 0.6)} 0)\n"
                f"\t\t\t{font(1.27, ' (justify left top)')})\n")
        for k in range(1, cm.NUM_NETS + 1):
            py = sy + 3.81 + (k - 1) * pitch
            out += (f"\t\t(pin \"{cm.net_name(k)}\" bidirectional (at {fmt(sx + w)} {fmt(py)} 0)\n"
                    f"\t\t\t(uuid \"{uid('sheetpin', name, k)}\") {font(1.27, ' (justify right)')})\n")
        out += (f"\t\t(instances (project \"{PROJECT}\" (path \"/{ROOT_UUID}\" (page \"{n + 2}\"))))\n\t)\n")
        for k in range(1, cm.NUM_NETS + 1):
            py = sy + 3.81 + (k - 1) * pitch
            lx = sx + w + 7.62
            out += wire(sx + w, py, lx, py, ("root", name, k))
            out += (f"\t(global_label \"{cm.net_name(k)}\" (shape bidirectional) (at {fmt(lx)} {fmt(py)} 0)\n"
                    f"\t\t(fields_autoplaced yes) {font(1.27, ' (justify left)')}\n"
                    f"\t\t(uuid \"{uid('glabel', name, k)}\")\n"
                    f"\t\t(property \"Intersheetrefs\" \"${{INTERSHEET_REFS}}\" (at {fmt(lx)} {fmt(py)} 0)\n"
                    f"\t\t\t{font(1.27, ' (justify left) (hide yes)')}))\n")
    out += "\t(sheet_instances (path \"/\" (page \"1\")))\n"
    return out + "\t(embedded_fonts no)\n)\n"


def main():
    omitted = cm.verify()
    assert len(omitted) == 20
    sheet_uuids = [uid("sheet", name) for name, _ in HALVES]
    SUB_FILE.write_text(build_subsheet(sheet_uuids), encoding="utf-8", newline="\n")
    ROOT_FILE.write_text(build_root(sheet_uuids), encoding="utf-8", newline="\n")
    print(f"wrote {ROOT_FILE.name} and {SUB_FILE.name}")


if __name__ == "__main__":
    main()
