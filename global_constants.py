CELL_LIMIT = 1000
LVL_0_INTEL_LIM = 900
LVL_1_INTEL_LIM = 90
LVL_2_INTEL_LIM = 9

# ----------------------------------------------------------------------
# Cell division (mitosis) tuning -- see Cell.split / Cell.update_split
# ----------------------------------------------------------------------
# Speed (px/s) each daughter slides along the split axis while the pair is
# pulling apart. The two daughters move in opposite directions, so the gap
# between them opens at roughly 2 * SPLIT_SPEED. Lower = slower, more visible
# mitosis; higher = snappier.
SPLIT_SPEED = 20.0

# The split is finished when distance(d1, d2) >= r1 + r2 + this margin (px).
# The small margin stops the pair touching again on the very next frame.
SPLIT_SEPARATION_MARGIN = 1.0

# A parent slower than this (px/s) counts as "not moving": the split axis is
# then a random direction instead of the parent's velocity direction.
SPLIT_MIN_PARENT_SPEED = 1.0

# Safety nets so a pair can never stay in the splitting state forever (e.g.
# both daughters wedged against terrain). Neither is the normal way a split
# ends -- that is always the geometric distance test above.
SPLIT_STALL_TIME = 0.5     # s without the gap growing -> try a new split axis
SPLIT_MAX_DURATION = 6.0   # s hard cap -> force the pair back to normal

# Seconds of invulnerability each daughter gets, counted from the moment the
# separation FINISHES (not from when the split begins).
POST_SPLIT_INVULNERABILITY = 3.0

# Draw a faint fading ring around a cell while it is post-split invulnerable.
SHOW_INVULNERABILITY_RING = True

# While two daughters still overlap, draw them as ONE silhouette: the parts of
# each outline that lie inside the other cell are hidden, so the border reads
# as a single cell pinching in two (see Cell._draw_split_pair). False = plain
# overlapping outlines. Rendering only -- the split mechanics don't change.
SPLIT_MERGE_OUTLINES = True

# Thickness (screen px) of every cell's outline. The mitosis mask is inset by
# exactly this much, so it follows along if you thicken the border.
CELL_OUTLINE_WIDTH = 1
