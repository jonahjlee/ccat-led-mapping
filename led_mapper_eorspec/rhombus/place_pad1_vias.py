import pcbnew

board = pcbnew.GetBoard()
design_settings = board.GetDesignSettings()

via_size = design_settings.GetCurrentViaSize()
via_drill = design_settings.GetCurrentViaDrill()
track_width = design_settings.GetCurrentTrackWidth()

triangle_height_mm = 1.810
triangle_base_mm = 2.090

offset_x = pcbnew.FromMM(triangle_base_mm/4)  # positive Y = down on the canvas
offset_y = pcbnew.FromMM(triangle_height_mm/2)

count = 0
skipped = []

for fp in board.GetFootprints():
    ref = fp.GetReference()
    if not ref.startswith("D"):
        continue

    pad1 = fp.FindPadByNumber("1")
    pad2 = fp.FindPadByNumber("2")
    if pad1 is None or pad2 is None:
        skipped.append(ref)
        continue

    pad1_pos = pad2.GetPosition()
    pad2_pos = pad2.GetPosition()
    net = pad1.GetNet()

    fp_pos = fp.GetPosition()
    via_pos = pcbnew.VECTOR2I(pad2_pos.x + offset_x, pad2_pos.y + offset_y)

    # Via
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(via_pos)
    via.SetWidth(via_size)
    via.SetDrill(via_drill)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)

    # Track from pad 1 to via
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pad1_pos)
    track.SetEnd(via_pos)
    track.SetWidth(track_width)
    track.SetLayer(pcbnew.F_Cu)
    track.SetNet(net)
    board.Add(track)

    count += 1

pcbnew.Refresh()
print(f"Placed {count} via+track pairs.")
if skipped:
    print(f"Skipped (no pad '1' found): {skipped}")