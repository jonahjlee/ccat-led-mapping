# ============================================================================ #
# led_placer.py
#
# Jonah Lee
# CCAT Prime 2025
#
# Lay out PCB. 
# KiCAD script to place LEDs for 850GHz LED mapping
# Mirrored across the y=0 axis.
# Does not contain routing methods - use led_placer and then mirror the tracks & vias across the y=0 axis.
# ============================================================================ #

import pcbnew
from math import cos, sin, radians

active_pcb = pcbnew.GetBoard()

class LedPlacerMirrored:

    def __init__(self, network: int, pcb: pcbnew.BOARD=active_pcb):

        valid_networks = {1, 2, 3, 4}
        assert network in valid_networks, f"network must be one of: {valid_networks}"
        self.network = network  # charlieplexed network id

        self.pcb = pcb

        self.layertable: dict[str, int] = self.get_layertable()
        self.front_copper_layer: int = self.layertable['F.Cu']
        self.inner_layer_1 = self.layertable['In1.Cu']
        self.inner_layer_2 = self.layertable['In2.Cu']
        self.back_copper_layer: int = self.layertable['B.Cu']

        # constants based on led_mapper_850.kicad_sch
        # rows and columns refer to position on pcb, not in schematic,
        # though the schematic is on the same grid except discontinuities where diagonals are missing
        # for example, D69 is in column 23 and not column 24
        self.num_rows = 12  # actual num rows is 11.5; last row contains only 23 LEDs
        self.num_cols = 46

        # constants based on pixel_loc_analysis.xlsx
        # LEDs lie on a hexagonal grid composed of equilateral triangles with side length equal to self.spacing_um
        self.spacing_um = 1400.0
        # below are magnitudes only, directions change for different networks
        self.row_shift_um = self.spacing_um / 2
        self.col_width_um = self.spacing_um
        self.row_height_um = (self.spacing_um ** 2 - self.row_shift_um ** 2) ** 0.5

        self.reference_led, self.leds, self.reference_x_um, self.reference_y_um = self.get_leds()

        self.connector_ref = f'J1'
        self.connector_via_dist_um = 3000

        self.auto_refresh = True  # set to false if kicad crashes when running placement methods

    # =====================================================
    # PLACEMENT METHODS - MODIFY THE PCB
    # =====================================================

    def place_leds(self) -> None:
        """Place LEDs in a 46x11.5 hexagonal grid"""
        for row_idx in range(self.num_rows):
            row = row_idx + 1
            for col_idx in range(self.num_cols):
                col = col_idx + 1

                # last row is half full
                if row == self.num_rows and col > self.num_cols // 2: continue

                ref = self.led_ref(row, col)
                fp: pcbnew.FOOTPRINT = self.pcb.FindFootprintByReference(ref)
                assert fp is not None, f"footprint with refdes: '{ref}' not found!"

                if ref == self.reference_led:
                    x_um = self.reference_x_um
                    y_um = self.reference_y_um
                else:
                    if self.network in (1, 3):
                        x_um = self.reference_x_um - col_idx * self.col_width_um + row_idx * self.row_shift_um
                        y_um = self.reference_y_um + row_idx * self.row_height_um
                    else:
                        x_um = self.reference_x_um + col_idx * self.col_width_um - row_idx * self.row_shift_um
                        y_um = self.reference_y_um - row_idx * self.row_height_um

                self.set_microns(fp, x_um, y_um)
                orientation_deg = 120
                fp.SetOrientationDegrees(orientation_deg)
        self.refresh()

    # =====================================================
    # HELPER METHODS
    # =====================================================

    def led_footprint(self, row: int, col: int) -> pcbnew.FOOTPRINT:
        return self.pcb.FindFootprintByReference(self.led_ref(row, col))

    def led_ref(self, row: int, col: int) -> str:
        """Get the refdes of an LED given its position in the grid.

        This method will break if the schematic is changed.

        :param int row: The row of the LED in the rectangular grid, from top (row 1) to bottom (row 12)
        :param int col: The column of the LED in the rectangular grid, from left (col 1) to right (col 46)
        :return int: LED refdes
        """
        network_offset = (self.network - 1) * 529
        return f'D{self.led_id(row, col) + network_offset}'

    def led_id(self, row: int, col: int) -> int:
        """Get the id of an LED given its position in the grid.

        This method will break if the schematic is changed.

        :param int row: The row of the LED in the rectangular grid, from top (row 1) to bottom (row 12)
        :param int col: The column of the LED in the rectangular grid, from left (col 1) to right (col 46)
        :return int: LED id
        """
        assert 1 <= row <= self.num_rows, f"row {row} is outside the grid!"
        assert 1 <= col <= self.num_cols, f"column {col} is outside the grid!"
        half_cols = self.num_cols // 2
        assert not (row == self.num_rows and col > half_cols), \
            f"final row (row {self.num_rows}) is only half-full, with LEDs from col 1 - {half_cols}!"

        row_idx = row - 1
        return row_idx * self.num_cols + col

    def set_microns(self, item: pcbnew.EDA_ITEM, x_um: float, y_um: float) -> None:
        item.SetPosition(self.vector2i_um(x_um, y_um))

    @staticmethod
    def vector2i_um(x_um: float, y_um: float) -> pcbnew.VECTOR2I:
        return pcbnew.VECTOR2I(int(x_um * 1000), int(y_um * 1000))

    def get_layertable(self) -> dict[str, int]:
        layertable: dict[str, int] = {}
        for i in range(1000):
            name = self.pcb.GetLayerName(i)
            if name != "BAD INDEX!":
                layertable[name] = i
        return layertable

    def get_leds(self) -> tuple[str, list[pcbnew.FOOTPRINT], float, float]:
        if self.network == 1:
            reference_led = 'D1'
            leds: list[pcbnew.FOOTPRINT] = [self.pcb.FindFootprintByReference(f'D{ref_id}') for ref_id in range(1, 530)]
            reference_x_um = 0.0
            reference_y_um = 0.0
        elif self.network == 2:
            reference_led = 'D530'
            leds: list[pcbnew.FOOTPRINT] = [self.pcb.FindFootprintByReference(f'D{ref_id}') for ref_id in range(530, 1059)]
            reference_x_um = -45 * self.col_width_um + 22 * self.row_shift_um
            reference_y_um = 22 * self.row_height_um
        elif self.network == 3:
            reference_led = 'D1059'
            leds: list[pcbnew.FOOTPRINT] = [self.pcb.FindFootprintByReference(f'D{ref_id}') for ref_id in range(1059, 1588)]
            reference_x_um = 23 * self.row_shift_um
            reference_y_um = 23 * self.row_height_um
        else:
            assert self.network == 4, "invalid network ID!"
            reference_led = 'D1588'
            leds: list[pcbnew.FOOTPRINT] = [self.pcb.FindFootprintByReference(f'D{ref_id}') for ref_id in range(1588, 2117)]
            reference_x_um = -45 * self.col_width_um + 45 * self.row_shift_um
            reference_y_um = 45 * self.row_height_um
        return reference_led, leds, reference_x_um, reference_y_um

    def refresh(self):
        if self.auto_refresh:
            pcbnew.Refresh()