# A REAL optimization of the example target's `solve` (sum of squares).
# Vectorized with numpy: same answer as the reference loop, far faster. The layered
# oracle verifies it stays correct on withheld + adversarial inputs, then credits
# the speedup. This is what a good candidate looks like.
import numpy as np


def solve(x):
    arr = np.asarray(x, dtype=float)
    return float(arr @ arr)
