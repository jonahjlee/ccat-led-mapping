"""Generate the project footprint library (eorspec.pretty) and register it in the project fp-lib-table.

LED_0201_XL-0201SURC: based on the XINGLIGHT XL-0201SURC datasheet pattern
(0.24 x 0.28 pads, 0.58 span, 0.10 gap), enlarged slightly to meet JLCPCB's
minimum SMD pad (0.25 x 0.25) and pad-to-pad spacing (0.15): pads 0.25 x 0.30 mm
at +/-0.20 mm (0.15 gap, 0.65 span = body length). Still well under the stock
IPC 0201 pads (0.46 x 0.40), to reduce tombstoning. Paste shrunk 10 um per side (~85% area).
Pad 1 = cathode (left), pad 2 = anode (right), matching Device:LED.
No silkscreen (2.09 mm pitch is too dense); reference on F.Fab only.
"""
import uuid
from pathlib import Path

PRJ_DIR = Path(__file__).resolve().parent.parent / "kicad-32x32" / "eorspec_rhombus"
LIB_NAME = "eorspec"
LIB_DIR = PRJ_DIR / f"{LIB_NAME}.pretty"
FP_NAME = "LED_0201_XL-0201SURC"

PAD_W, PAD_H, PAD_X = 0.25, 0.30, 0.20
PASTE_MARGIN = -0.01
BODY_L, BODY_W = 0.65, 0.35
CRT_X, CRT_Y = 0.45, 0.30


def uid(k):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"eorspec_rhombus/fp/{FP_NAME}/{k}"))


def stroke(w):
    return f"(stroke (width {w}) (type solid))"


def fp_text() -> str:
    hx, hy = BODY_L / 2, BODY_W / 2
    font = "(effects (font (size 0.25 0.25) (thickness 0.04)))"
    out = f"""(footprint "{FP_NAME}"
	(version 20260206)
	(generator "eorspec_scripts")
	(layer "F.Cu")
	(descr "XINGLIGHT XL-0201SURC 0201 LED, 0.25x0.30 pads, 0.15 gap (datasheet pattern widened to JLCPCB minimums)")
	(tags "LED 0201 XL-0201SURC")
	(property "Reference" "REF**" (at 0 -0.4 0) (layer "F.Fab") (uuid "{uid('ref')}") {font})
	(property "Value" "XL-0201SURC" (at 0 0.4 0) (layer "F.Fab") (hide yes) (uuid "{uid('val')}") {font})
	(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid('ds')}") {font})
	(property "Description" "0201 red LED" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid('desc')}") {font})
	(attr smd)
	(fp_rect (start {-hx} {-hy}) (end {hx} {hy}) {stroke(0.05)} (fill no) (layer "F.Fab") (uuid "{uid('body')}"))
	(fp_line (start -0.2 {-hy}) (end -0.2 {hy}) {stroke(0.05)} (layer "F.Fab") (uuid "{uid('kbar')}"))
	(fp_rect (start {-CRT_X} {-CRT_Y}) (end {CRT_X} {CRT_Y}) {stroke(0.05)} (fill no) (layer "F.CrtYd") (uuid "{uid('crt')}"))
"""
    for num, x in (("1", -PAD_X), ("2", PAD_X)):
        out += (f'\t(pad "{num}" smd roundrect (at {x} 0) (size {PAD_W} {PAD_H}) (layers "F.Cu" "F.Paste" "F.Mask")\n'
                f'\t\t(roundrect_rratio 0.15) (solder_paste_margin {PASTE_MARGIN}) (uuid "{uid("pad" + num)}"))\n')
    out += """	(model "${KICAD10_3DMODEL_DIR}/LED_SMD.3dshapes/LED_0201_0603Metric.step"
		(offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
	(embedded_fonts no)
)
"""
    return out


def ensure_lib_table():
    table = PRJ_DIR / "fp-lib-table"
    entry = (f'  (lib (name "{LIB_NAME}")(type "KiCad")(uri "${{KIPRJMOD}}/{LIB_NAME}.pretty")'
             f'(options "")(descr "Project footprints"))\n')
    if table.exists():
        text = table.read_text(encoding="utf-8")
        if f'(name "{LIB_NAME}")' in text:
            return
        text = text.rstrip().rstrip(")") + entry + ")\n"
    else:
        text = "(fp_lib_table\n  (version 7)\n" + entry + ")\n"
    table.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    LIB_DIR.mkdir(exist_ok=True)
    (LIB_DIR / f"{FP_NAME}.kicad_mod").write_text(fp_text(), encoding="utf-8", newline="\n")
    ensure_lib_table()
    print(f"wrote {LIB_DIR.name}/{FP_NAME}.kicad_mod and fp-lib-table")
