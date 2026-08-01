import numpy as np
import random


def sa_sequence(matrix, member_indices, max_iter=8000, seed=None):
    """
    Simulated annealing to reorder elements within a cluster.
    Minimises feedback marks (marks above the diagonal, i.e. an element
    depending on one that comes later in sequence).

    seed: int or None. Pass an explicit seed for reproducible output.
    Uses a local Random instance so it never mutates global RNG state
    (safe to call from multiple clusters without cross-talk).

    Returns reordered list of original indices.
    """
    if len(member_indices) <= 2:
        return member_indices

    rng = random.Random(seed)

    sub = matrix[np.ix_(member_indices, member_indices)]
    n = len(member_indices)
    order = list(range(n))
    cost = _feedback(sub, order)
    best_order, best_cost = order[:], cost

    t_start, t_end = 1.0, 0.001
    for step in range(max_iter):
        t = t_start * (t_end / t_start) ** (step / max_iter)
        i, j = sorted(rng.sample(range(n), 2))
        order[i], order[j] = order[j], order[i]
        new_cost = _feedback(sub, order)
        if new_cost < cost or rng.random() < np.exp(-(new_cost - cost) / max(t, 1e-12)):
            cost = new_cost
            if cost < best_cost:
                best_order, best_cost = order[:], cost
        else:
            order[i], order[j] = order[j], order[i]   # revert

    return [member_indices[i] for i in best_order]


def _feedback(sub, order):
    """
    Sum of marks strictly above the diagonal after reordering (row position <
    column position). Under the row-depends-on-column DSM convention, these
    are the feedback marks: a dependency on something that hasn't happened
    yet in the sequence. Vectorized with numpy for speed.

    Internal hot-loop helper: takes an already-sliced submatrix and a *local*
    (0..n-1) order, so it can be called thousands of times inside the SA loop
    without re-slicing the full matrix each time.
    """
    reordered = sub[np.ix_(order, order)]
    return np.triu(reordered, k=1).sum()


def feedback_marks(matrix, member_indices):
    """
    Public convenience wrapper: feedback mark count for a list of *global*
    indices, in the order given. Used for reporting (e.g. "before" using the
    original member order, "after" using sa_sequence's returned order) -
    not performance-critical, so it's fine to re-slice here.
    """
    sub = matrix[np.ix_(member_indices, member_indices)]
    return int(np.triu(sub, k=1).sum())
