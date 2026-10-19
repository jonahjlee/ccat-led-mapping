"""Pin-pair mapping for one charlieplexed network (one half of the 32x32 rhombus).

Each half is 16 rows x 32 LEDs. Adjacent LED columns (2c, 2c+1) form a "pair cell"
of two antiparallel LEDs sharing the same two nets, giving a 16x16 grid of cells.

Each cell (r, c) has two nets:
  h - reached by a horizontal (row) track
  v - reached by a 60-degree (rhombus column) track

Net groups: A = P01-P08, B = P09-P16, C = P17-P24. Quadrants of the cell grid
(8x8 each, r/c 0-based, i/j = 1-based index within the quadrant):
  top-left     A_i x B_j
  top-right    A_i x C_j
  bottom-left  C_i x B_j
  bottom-right i<j: C_i x C_j,  i>j: B_i x B_j,  i==j: A_i x A_(i+1) (ring)

This uses 256 of the 276 pin pairs; the 20 unused pairs are all within group A.

LEDs within a cell (both in the same footprint orientation, pad 1 = cathode on the left):
  left  LED (col 2c):   cathode = h, anode = v
  right LED (col 2c+1): cathode = v, anode = h
so the pads along the row read  [h v][v h].

Both halves use the same map. Refs: top half D1-D512, bottom half D513-D1024,
ref = 1 + 512*half + 32*row + col.

Board placement: the two networks are 180-degree rotations of each other about the
board centre. The bottom network sits as drawn (map row 0 at the seam, row 15 at the
bottom edge); the top network is rotated 180 (map row 0 at the seam, row 15 at the top
edge). Each network's connecting tracks to its second segments therefore run along the outer edges.
Board rows R = 0..31 top to bottom, board cols C = 0..31; each row is shifted left by
half a pitch from the row above. Positions are mm relative to the array centre, y down.

Run directly to (re)write the mapping CSV.
"""
import csv
import math
from itertools import combinations
from pathlib import Path

ROWS, COLS = 16, 32            # LEDs per half
CELL_ROWS, CELL_COLS = 16, 16  # pair cells per half
LEDS_PER_HALF = ROWS * COLS
NUM_NETS = 24

CSV_PATH = Path(__file__).resolve().parent.parent / "kicad-32x32" / "led_map.csv"


def net_name(n: int) -> str:
    return f"P{n:02d}"


def cell_nets(r: int, c: int) -> tuple[int, int, str]:
    """(h, v, region) for pair cell (r, c), nets numbered 1-24."""
    i, j = r % 8 + 1, c % 8 + 1
    A, B, C = (lambda k: k), (lambda k: 8 + k), (lambda k: 16 + k)
    if r < 8 and c < 8:
        return A(i), B(j), "AxB"
    if r < 8:
        return A(i), C(j), "AxC"
    if c < 8:
        return C(i), B(j), "CxB"
    if i < j:
        return C(i), C(j), "CxC"
    if i > j:
        return B(i), B(j), "BxB"
    return A(i), A(i % 8 + 1), "Aring"


def ref(half: int, row: int, col: int) -> str:
    return f"D{1 + LEDS_PER_HALF * half + COLS * row + col}"


PITCH = 2.09                         # mm between LEDs in a row
ROW_H = PITCH * math.sqrt(3) / 2     # mm between rows (~1.810)


def board_rc(half: int, row: int, col: int) -> tuple[int, int, int]:
    """(board row, board col, rotation deg) of a map position. half 0 = top network."""
    if half == 0:
        return ROWS - 1 - row, COLS - 1 - col, 180
    return ROWS + row, col, 0


def board_xy(R: int, C: int) -> tuple[float, float]:
    """mm relative to the array centre (y down)."""
    x = PITCH * C - PITCH / 2 * R
    y = ROW_H * R
    xc, yc = PITCH * 15.5 - PITCH / 2 * 15.5, ROW_H * 15.5
    return x - xc, y - yc


def leds():
    """Yield one dict per LED position in a half (same map for both halves)."""
    for row in range(ROWS):
        for col in range(COLS):
            cr, cc = row, col // 2
            h, v, region = cell_nets(cr, cc)
            cathode, anode = (h, v) if col % 2 == 0 else (v, h)
            d = {
                "row": row, "col": col, "cell_row": cr, "cell_col": cc,
                "ref_top": ref(0, row, col), "ref_bottom": ref(1, row, col),
                "anode": net_name(anode), "cathode": net_name(cathode),
                "region": region,
            }
            for half, tag in ((0, "top"), (1, "bottom")):
                R, C, rot = board_rc(half, row, col)
                x, y = board_xy(R, C)
                d.update({f"board_row_{tag}": R, f"board_col_{tag}": C,
                          f"x_{tag}_mm": round(x, 4), f"y_{tag}_mm": round(y, 4), f"rot_{tag}": rot})
            yield d


def verify() -> list[tuple[int, int]]:
    """Check every cell is a distinct, non-self pair. Returns the omitted pairs."""
    seen = {}
    for r in range(CELL_ROWS):
        for c in range(CELL_COLS):
            h, v, _ = cell_nets(r, c)
            assert h != v, f"cell {(r, c)} pairs {net_name(h)} with itself"
            key = frozenset((h, v))
            assert key not in seen, f"pair {sorted(key)} at {(r, c)} and {seen[key]}"
            seen[key] = (r, c)
    every = {frozenset(p) for p in combinations(range(1, NUM_NETS + 1), 2)}
    return sorted(tuple(sorted(p)) for p in every - set(seen))


def write_csv(path: Path = CSV_PATH) -> None:
    rows = list(leds())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    omitted = verify()
    print(f"{CELL_ROWS * CELL_COLS} pair cells OK, {len(omitted)} pairs unused:",
          ", ".join(f"{net_name(a)}-{net_name(b)}" for a, b in omitted))
    write_csv()
    print(f"wrote {CSV_PATH}")
