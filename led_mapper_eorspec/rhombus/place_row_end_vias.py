import pcbnew

board = pcbnew.GetBoard()
design_settings = board.GetDesignSettings()

via_size = design_settings.GetCurrentViaSize()
via_drill = design_settings.GetCurrentViaDrill()
track_width = design_settings.GetCurrentTrackWidth()

FIRST_ID = 481
LAST_ID = 512

triangle_height_mm = 1.810
triangle_base_mm = 2.090

offset_x = pcbnew.FromMM(triangle_base_mm / 4)   # magnitude only, applied leftward below
offset_y = pcbnew.FromMM(triangle_height_mm / 2)  # positive Y = down on the canvas

count = 0
skipped = []

for ref_id in range(FIRST_ID, LAST_ID + 1):
    ref = f"D{ref_id}"
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        skipped.append(ref)
        continue

    pad2 = fp.FindPadByNumber("2")
    if pad2 is None:
        skipped.append(ref)
        continue

    pad2_pos = pad2.GetPosition()
    net = pad2.GetNet()

    # Same offset magnitudes as before, but mirrored to the left (-x)
    via_pos = pcbnew.VECTOR2I(pad2_pos.x - offset_x, pad2_pos.y + offset_y)

    # Via
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(via_pos)
    via.SetWidth(via_size)
    via.SetDrill(via_drill)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)

    # Track from pad 2 to via
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pad2_pos)
    track.SetEnd(via_pos)
    track.SetWidth(track_width)
    track.SetLayer(pcbnew.F_Cu)
    track.SetNet(net)
    board.Add(track)

    count += 1

pcbnew.Refresh()
print(f"Placed {count} via+track pairs.")
if skipped:
    print(f"Skipped (missing footprint or pad 2): {skipped}")