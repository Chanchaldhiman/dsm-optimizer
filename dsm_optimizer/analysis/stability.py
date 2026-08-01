"""
Clustering stability / consensus analysis.

Answers the question every skeptical engineer asks of a stochastic
clustering: "would I get the same modules tomorrow?" Run the chosen
algorithm N times with different seeds; the co-clustering matrix
C[i][j] = fraction of runs in which elements i and j landed in the same
cluster. Entries near 1.0 are robust module assignments; entries near
0.5 are coin flips the engineer should decide manually.

Per-element consistency = mean co-clustering frequency with the members
of its own reference cluster (the partition being displayed) — a direct
"how settled is this element" score.
"""
import numpy as np
from ..algorithms.spectral import spectral_cluster
from ..algorithms.thebeau import thebeau_cluster
from ..algorithms.louvain import louvain_cluster


def stability_analysis(matrix, algorithm, reference_clusters,
                       runs=20, min_k=2, max_k=10, base_seed=0):
    """
    matrix: CORE matrix (bus elements already excluded).
    algorithm: 'spectral' | 'thebeau' | 'louvain' (MCL is deterministic —
               reject it upstream with a clear message).
    reference_clusters: the partition currently on screen, in the SAME
               element order as `matrix` (used for consistency scores).

    Returns dict: co_cluster (n x n floats), consistency (per element),
    runs, n_distinct_partitions.
    """
    n = len(matrix)
    co = np.zeros((n, n))
    partitions = set()

    for r in range(runs):
        seed = base_seed + r
        if algorithm == "spectral":
            cl, _, _ = spectral_cluster(matrix, min_k=min_k, max_k=max_k, seed=seed)
        elif algorithm == "thebeau":
            cl = thebeau_cluster(matrix, seed=seed)
        elif algorithm == "louvain":
            cl = louvain_cluster(matrix, seed=seed)
        else:
            raise ValueError(f"Stability analysis not supported for '{algorithm}'.")
        partitions.add(tuple(cl))
        cl = np.asarray(cl)
        same = (cl[:, None] == cl[None, :])
        co += same

    co /= runs
    np.fill_diagonal(co, 1.0)

    ref = np.asarray(reference_clusters)
    consistency = []
    for i in range(n):
        peers = [j for j in range(n) if j != i and ref[j] == ref[i]]
        consistency.append(float(np.mean(co[i, peers])) if peers else 1.0)

    return {
        "co_cluster": co,
        "consistency": consistency,
        "runs": runs,
        "n_distinct_partitions": len(partitions),
        "mean_consistency": float(np.mean(consistency)),
    }
