import numpy as np


def run_mcl(matrix, expansion=2, inflation=2.0, iterations=100, tol=1e-6):
    """
    Markov Clustering Algorithm (MCL) - self-contained implementation.
    Works directly on DSM adjacency matrix.
    """
    M = matrix.astype(float).copy()
    np.fill_diagonal(M, 1.0)        # add self-loops
    M = _col_normalize(M)

    for _ in range(iterations):
        prev = M.copy()
        M = np.linalg.matrix_power(M, expansion)   # expand
        M = np.power(M, inflation)                   # inflate
        M = _col_normalize(M)
        if np.max(np.abs(M - prev)) < tol:
            break

    return _extract_clusters(M)


def _col_normalize(M):
    col_sums = M.sum(axis=0)
    col_sums[col_sums == 0] = 1.0
    return M / col_sums


def _extract_clusters(M):
    n = M.shape[0]
    # Attractors: nodes that are their own strongest attractor
    attractors = [i for i in range(n) if M[i, i] > 0]
    if not attractors:
        attractors = [np.argmax(M[:, i]) for i in range(n)]

    clusters = [-1] * n
    for cid, attr in enumerate(attractors):
        for node in range(n):
            if M[attr, node] > 0 and clusters[node] == -1:
                clusters[node] = cid

    # Assign any unassigned nodes to nearest attractor
    for i in range(n):
        if clusters[i] == -1:
            best = max(range(len(attractors)),
                       key=lambda a: M[attractors[a], i])
            clusters[i] = best

    # Re-label 0..k
    unique = sorted(set(clusters))
    remap = {old: new for new, old in enumerate(unique)}
    return [remap[c] for c in clusters]
