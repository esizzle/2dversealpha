# ======================================================================
# Simulation clock
# ----------------------------------------------------------------------
# Seconds of SIMULATED time since the game started. Game.update() advances it
# by the same fixed dt it hands to the physics step, so anything stamped
# against it (e.g. Cell.invulnerable_until) stays in step with the simulation
# even if the real frame rate dips or a deep profile stalls a frame.
#
# Same pattern as the `audio` singleton: one shared instance, import it
# wherever a timestamp is needed:
#     from sim_clock import sim_clock
# ======================================================================


class SimClock:
    def __init__(self):
        self.now = 0.0

    def tick(self, dt):
        self.now += dt


sim_clock = SimClock()
