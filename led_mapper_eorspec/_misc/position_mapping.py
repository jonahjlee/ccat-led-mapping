# ============================================================================ #
# position_mapping.py
#
# Jonah Lee
# CCAT Prime 2025
#
# Functions to map between LED 'refdes' references, pin logic states
# and LED positions (row/column, or positions in um).
# NOTE: Pin indices start at 0 -- i.e. a 24 pin connector has pins 0-23, inclusive.
#       This fact may conflict with KiCAD PCB/Schematic designs
# ============================================================================ #

class LEDPositions850:

    def __init__(self):
        self.num_rows = 12
        self.num_cols = 46

    def led_id(self, row: int, col: int, network: int=1) -> int:
        """Get the id of an LED given its position in the grid.

        This method will break if the schematic is changed.

        :param int row: The row of the LED in the rectangular grid, from top (row 1) to bottom (row 12)
        :param int col: The column of the LED in the rectangular grid, from left (col 1) to right (col 46)
        :param int network: The network ([1,4]) of the LED. Each network has its own row/col grid.
        :return int: LED id
        """
        assert 1 <= row <= self.num_rows, f"row {row} is outside the grid!"
        assert 1 <= col <= self.num_cols, f"column {col} is outside the grid!"
        half_cols = self.num_cols // 2
        assert not (row == self.num_rows and col > half_cols), \
            f"final row (row {self.num_rows}) is only half-full, with LEDs from col 1 - {half_cols}!"

        row_idx = row - 1
        network_1_id = row_idx * self.num_cols + col

        return network_1_id + (network - 1) * 529

    def led_position(self, led_id: int) -> tuple[int, int]:
        """Get the row and column of an LED given its ID.

        This method will break if the schematic is changed.

        :param int led_id: The ID of the LED.
        :return tuple: (row, col) position of the LED.
        """
        delta = 0.001  # error for float comparison
        assert 0 <= led_id < self.num_rows * (self.num_cols - 0.5) + delta, f"led_id {led_id} is outside the valid range!"
        row = led_id // self.num_cols
        col = led_id % self.num_cols
        if col == 0:
            col = self.num_cols
            row -= 1
        return row + 1, col

def test_pos_mapper():
    pos_mapper = LEDPositions850()
    for led_id  in range(1, 529 + 1):
        row, col = pos_mapper.led_position(led_id)
        out_id = pos_mapper.led_id(row, col)
        assert led_id == out_id, f"FAIL for {led_id=}, got {out_id=}."
        print(f"LED ID {led_id} passes the test!")


def diode_finder_interactive():
    pos_mapper = LEDPositions850()
    while True:
        input_str = input("Enter the LED ref number (int): ")
        try:
            led_refnum = int(input_str)
        except ValueError:
            print("Non-integer entered, exiting program...")
            break
        led_id = (led_refnum - 1) % 529 + 1
        led_net = (led_refnum - 1) // 529 + 1
        print(f"(row, col): {pos_mapper.led_position(led_id)}, {led_net=}")



if __name__ == "__main__":

    # test_pos_mapper()

    diode_finder_interactive()
