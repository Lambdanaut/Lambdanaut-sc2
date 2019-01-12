def ramp_point_nearest_point(ramps, p):
    # UNUSED RIGHT NOW
    for ramp in ramps:
        ramp_point = ramp.bottom_center

        return p.closest(ramp_point)
