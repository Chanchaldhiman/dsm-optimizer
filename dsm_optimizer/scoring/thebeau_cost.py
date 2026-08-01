import numpy as np


def thebeau_cost(matrix, clusters, pow_cc=1.0, pow_bid=1.0):
    """
    Thebeau coordination cost.
    Low cost = good clustering (high intra, low extra).
    """
    n = len(matrix)
    unique = set(clusters)
    total = 0.0

    for c in unique:
        members = [i for i, cl in enumerate(clusters) if cl == c]
        size = len(members)
        if size == 0:
            continue
        intra = sum(matrix[i][j] for i in members for j in members if i != j)
        extra = sum(matrix[i][j] for i in members for j in range(n)
                    if clusters[j] != c and matrix[i][j] > 0)
        if intra > 0:
            total += (intra ** 2) / (size ** pow_cc)
        total += extra * (n ** pow_bid)

    return total


def external_ratio(matrix, clusters):
    n = len(matrix)
    total_marks = matrix.sum()
    if total_marks == 0:
        return 0.0
    ext = sum(matrix[i][j] for i in range(n) for j in range(n)
              if i != j and clusters[i] != clusters[j] and matrix[i][j] > 0)
    return ext / total_marks
