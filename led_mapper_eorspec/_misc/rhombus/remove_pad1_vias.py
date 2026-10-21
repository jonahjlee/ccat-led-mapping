import pcbnew

board = pcbnew.GetBoard()

tracks_to_delete = []
vias_to_delete = []

# Build a lookup of all vias on the board by position
all_vias = [item for item in board.GetTracks() if isinstance(item, pcbnew.PCB_VIA)]
all_segments = [item for item in board.GetTracks() if not isinstance(item, pcbnew.PCB_VIA)]

for fp in board.GetFootprints():
    ref = fp.GetReference()
    if not ref.startswith("D"):
        continue

    pad2 = fp.FindPadByNumber("2")
    if pad2 is None:
        continue

    pad_pos = pad2.GetPosition()
    net = pad2.GetNetCode()

    # Find straight track segments with one end exactly at pad 1
    candidate_tracks = [
        t for t in all_segments
        if t.GetNetCode() == net and (t.GetStart() == pad_pos or t.GetEnd() == pad_pos)
    ]

    for track in candidate_tracks:
        # Determine the other end of the track (away from the pad)
        other_end = track.GetEnd() if track.GetStart() == pad_pos else track.GetStart()

        # Find a via sitting exactly at that other end, same net
        matching_vias = [
            v for v in all_vias
            if v.GetNetCode() == net and v.GetPosition() == other_end
        ]

        for via in matching_vias:
            # Safety check: only remove if this via has exactly one track
            # connected to it (i.e. it's not part of other routing)
            connected_segments = [
                t for t in all_segments
                if t.GetNetCode() == net and
                   (t.GetStart() == via.GetPosition() or t.GetEnd() == via.GetPosition())
            ]
            # if len(connected_segments) == 1:
            tracks_to_delete.append(track)
            vias_to_delete.append(via)

# Remove duplicates (in case of overlapping matches)
# tracks_to_delete = list(set(tracks_to_delete))
# vias_to_delete = list(set(vias_to_delete))

for track in tracks_to_delete:
    board.Remove(track)
for via in vias_to_delete:
    board.Remove(via)

pcbnew.Refresh()
print(f"Removed {len(tracks_to_delete)} tracks and {len(vias_to_delete)} vias.")