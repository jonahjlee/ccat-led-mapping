# Dimensions

This project will create a charlieplexed LED matrix PCB  with a 32x32 rhombus shaped grid of 0201 LEDs.

All LEDs shall be on a grid with the following specifications:
- LEDs are horizontal as seen in the KiCad PCB editor
- LEDs are on an equilateral triangle grid. Rows are horizontal, with LEDs spaced 2090um apart.
- Each row below the top row is offset by 2090/2 um to the left from the row above.
- The height between rows is sqrt(3)*2090/2 um, very cose to 1810um.

There are 24 nets / addressing wires that are the input to the board,
that are tri-state addressible to enable charlieplexing. The top half of the board
is addressed in parallel with the bottom half of the board such that
for every addressing high/low pair (with all other pins on high-impedance),
two LEDs turn on: one on the top and one on the bottom.

The specific mapping of pin pairs to (column, row) location of the LED is not
set, but it must be tracked and ideally simple to follow.