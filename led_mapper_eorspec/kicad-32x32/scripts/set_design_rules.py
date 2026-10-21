"""Apply JLCPCB 4-layer design rules to the project (.kicad_pro + .kicad_dru).

Source: https://jlcpcb.com/capabilities/pcb-capabilities (checked 2026-10-18), 1 oz outer copper.
  - Multilayer min track/space 0.09/0.09 mm  -> board minimum 0.09, routing default 0.10/0.10
  - Min via 0.15 hole / 0.25 dia, but 0.2-0.25 mm holes with dia < 0.45 mm (and any 0.1-0.15 mm hole)
    cost extra -> vias 0.45 dia / 0.2 drill (price-neutral), enforced as the board minimum
  - Via hole to track 0.2, via hole-to-hole 0.2, copper to routed edge >= 0.2 (we use 0.3)
  - SMD pad-to-pad (different nets) 0.15 -> custom rule in .kicad_dru
  - Silkscreen: min line 0.15, min text height 1.0, pad to silk 0.15
  - Soldermask expansion 1:1 (pad_to_mask_clearance 0, already set in the board)
Via-in-pad is not used (extra cost on 4-layer boards).

Close the project in KiCad before running (KiCad rewrites .kicad_pro on close).
"""
import json
from pathlib import Path

PRJ_DIR = Path(__file__).resolve().parent.parent / "kicad-32x32" / "eorspec_rhombus"
PRO = PRJ_DIR / "eorspec_rhombus.kicad_pro"
DRU = PRJ_DIR / "eorspec_rhombus.kicad_dru"

TRACK, CLEARANCE = 0.10, 0.10
VIA_DIA, VIA_DRILL = 0.45, 0.20

BOARD_MINIMUMS = {
    "min_clearance": 0.09,
    "min_track_width": 0.09,
    "min_via_diameter": VIA_DIA,
    "min_through_hole_diameter": VIA_DRILL,
    "min_via_annular_width": 0.1,
    "min_hole_to_hole": 0.2,
    "min_hole_clearance": 0.2,
    "min_copper_edge_clearance": 0.3,
    "min_silk_clearance": 0.15,
    "min_text_height": 1.0,
    "min_text_thickness": 0.15,
}

DRU_TEXT = """(version 1)

# JLCPCB: SMD pad to pad clearance (different nets) >= 0.15 mm
(rule "JLC SMD pad spacing"
\t(constraint clearance (min 0.15))
\t(condition "A.Type == 'Pad' && B.Type == 'Pad'"))
"""


def main():
    d = json.loads(PRO.read_text(encoding="utf-8"))
    ds = d["board"]["design_settings"]
    ds["rules"].update(BOARD_MINIMUMS)
    ds["track_widths"] = [0.0, TRACK, 0.15, 0.2]               # first entry = "use netclass"
    ds["via_dimensions"] = [{"diameter": 0.0, "drill": 0.0},   # first entry = "use netclass"
                            {"diameter": VIA_DIA, "drill": VIA_DRILL}]
    for nc in d["net_settings"]["classes"]:
        if nc["name"] == "Default":
            nc.update(track_width=TRACK, clearance=CLEARANCE, via_diameter=VIA_DIA, via_drill=VIA_DRILL)
    PRO.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8", newline="\n")
    DRU.write_text(DRU_TEXT, encoding="utf-8", newline="\n")
    print(f"updated {PRO.name} and {DRU.name}")


if __name__ == "__main__":
    main()
