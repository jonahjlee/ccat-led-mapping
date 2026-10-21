"""Create the v2 KiCad project from the previous design (led_mapper_eorspec).

  - Schematic: led_mapper_eorspec.kicad_sch + single_net.kicad_sch copied byte for byte from
    led_mapper_eorspec/rhombus/, then ONLY the Footprint property of placed symbols is filled
    in: the 1024 LEDs get eorspec:LED_0201_XL-0201SURC and J1 moves from ccatlib: to eorspec:.
    The project keeps the name led_mapper_eorspec because the symbol instances (references
    D1-D1024, J1) are stored under that project name and the original root sheet UUID.
  - Project file: a clean project file (from kicad-32x32) with this project's sheet list,
    then the JLC design rules (scripts/set_design_rules.py) and .kicad_dru.
  - Footprints: project library eorspec.pretty (LED from scripts/gen_footprint.py, J1 copied
    from kicad-32x32) registered in fp-lib-table.
  - Board: the empty 4-layer board from the repo's first commit. LEDs are placed by
    place_leds.py.

Run with plain Python from anywhere; it refuses to overwrite an existing schematic.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import gen_footprint as gf          # noqa: E402
import set_design_rules as dr       # noqa: E402

NAME = "led_mapper_eorspec"
SRC = REPO / "led_mapper_eorspec" / "rhombus"
DST = REPO / "kicad-32x32-v2" / NAME
V1 = REPO / "kicad-32x32" / "eorspec_rhombus"
LED_FP = f"{gf.LIB_NAME}:{gf.FP_NAME}"
CONN_FP_NAME = "PinSocket_2x12_P2.54mm_Vertical_SMD_custom"
EMPTY_BOARD_COMMIT = "ba93421"
EMPTY_BOARD_PATH = "kicad-32x32/eorspec_rhombus/eorspec_rhombus.kicad_pcb"


def set_footprints(text: str) -> tuple[str, int]:
    """Fill the Footprint property inside placed symbols only (not the lib_symbols section)."""
    count = 0

    def fix(block: str) -> str:
        nonlocal count
        lib_id = re.search(r'\(lib_id "([^"]+)"\)', block).group(1)
        new = LED_FP if lib_id == "Device:LED_45deg" else (
            f"{gf.LIB_NAME}:{CONN_FP_NAME}" if lib_id.startswith("Connector_Generic:") else None)
        if new is None:
            return block
        out, n = re.subn(r'\(property "Footprint" "[^"]*"', f'(property "Footprint" "{new}"', block, count=1)
        count += n
        return out

    # placed symbols are top-level "(symbol" blocks: one tab deep, closed by "\n\t)"
    pattern = re.compile(r"(?ms)^\t\(symbol\r?\n.*?^\t\)")
    return pattern.sub(lambda m: fix(m.group(0)), text), count


def main():
    if (DST / f"{NAME}.kicad_sch").exists():
        sys.exit(f"{DST} already has a schematic; delete it first to recreate the project.")
    DST.mkdir(parents=True, exist_ok=True)

    total = 0
    for fname in (f"{NAME}.kicad_sch", "single_net.kicad_sch"):
        raw = (SRC / fname).read_bytes().decode("utf-8")
        text, n = set_footprints(raw)
        total += n
        (DST / fname).write_bytes(text.encode("utf-8"))
    print(f"copied schematic, set {total} Footprint fields")

    pro = json.loads((V1 / "eorspec_rhombus.kicad_pro").read_text(encoding="utf-8"))
    src_pro = json.loads((SRC / f"{NAME}.kicad_pro").read_text(encoding="utf-8"))
    pro["meta"]["filename"] = f"{NAME}.kicad_pro"
    pro["sheets"] = src_pro["sheets"]
    (DST / f"{NAME}.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n", encoding="utf-8", newline="\n")
    dr.main(DST / f"{NAME}.kicad_pro", DST / f"{NAME}.kicad_dru")

    gf.write_library(DST)
    shutil.copy2(V1 / f"{gf.LIB_NAME}.pretty" / f"{CONN_FP_NAME}.kicad_mod",
                 DST / f"{gf.LIB_NAME}.pretty" / f"{CONN_FP_NAME}.kicad_mod")

    board = subprocess.run(["git", "-C", str(REPO), "show", f"{EMPTY_BOARD_COMMIT}:{EMPTY_BOARD_PATH}"],
                           check=True, capture_output=True).stdout
    (DST / f"{NAME}.kicad_pcb").write_bytes(board)
    print(f"created {DST.relative_to(REPO)}")


if __name__ == "__main__":
    main()
