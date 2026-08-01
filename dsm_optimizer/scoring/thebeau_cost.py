import numpy as np


def thebeau_cost(matrix, clusters, pow_cc=1.0, pow_bid=1.0):
    """
    Thebeau coordination cost (Thebeau 2001), the published LINEAR form:

        cost = sum over dependencies d_ij of
                 d_ij * cluster_size^pow_cc   if i and j share a cluster
                 d_ij * n^pow_cc              otherwise

    Low cost = good clustering. Linear in the weights: a w=9 interface
    counts 9x a w=1 interface, inside or outside a cluster.

    Note: an earlier version of this file used a quadratic intra term
    (intra^2 / size). On binary matrices it behaves similarly, but on
    weighted matrices the quadratic blow-up actively pushes strong pairs
    OUT of clusters - the opposite of the intended objective. Fixed to
    the published formula.

    pow_bid is kept in the signature for backward compatibility with
    callers; the published cost does not use it.
    """
    n = len(matrix)
    counts = {}
    for c in clusters:
        counts[c] = counts.get(c, 0) + 1

    total = 0.0
    for i in range(n):
        row = matrix[i]
        ci = clusters[i]
        for j in range(n):
            w = row[j]
            if i == j or w <= 0:
                continue
            if clusters[j] == ci:
                total += w * (counts[ci] ** pow_cc)
            else:
                total += w * (n ** pow_cc)
    return total


def external_ratio(matrix, clusters):
    n = len(matrix)
    total_marks = matrix.sum()
    if total_marks == 0:
        return 0.0
    ext = sum(matrix[i][j] for i in range(n) for j in range(n)
              if i != j and clusters[i] != clusters[j] and matrix[i][j] > 0)
    return ext / total_marks