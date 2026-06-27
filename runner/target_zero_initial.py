# Target zero -- initial program for OpenEvolve to optimize.
#
# The task: compute the sum of a 1-D array of floats. This starting point is the
# slow, sequential reference. OpenEvolve (with Claude as proposer) will try to
# make `solve` faster. Our layered oracle (tripwire.evaluator) grades every
# candidate: it must stay correct on WITHHELD + adversarial inputs the optimizer
# never sees, so a memorization / skip-the-work hack earns zero reward (ADR-006).
#
# The entrypoint MUST be named `solve` (tripwire.evaluator.CANONICAL_ENTRYPOINT).

# EVOLVE-BLOCK-START
def solve(arr):
    """Sum a 1-D array of floats. Optimize me (keep the result correct)."""
    s = 0.0
    for x in arr:
        s += float(x)
    return s
# EVOLVE-BLOCK-END
