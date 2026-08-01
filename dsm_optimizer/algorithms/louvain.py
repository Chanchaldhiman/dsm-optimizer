"""
Louvain community detection — self-contained implementation (no networkx).

Operates on the symmetrised weighted graph W = (A + A^T)/2 and maximises
Newman-Girvan modularity. Standard two-phase scheme: (1) greedy local
moves of nodes between neighbouring communities until no gain, (2)
aggregate communities into super-nodes and repeat on the smaller graph.

Node visit order is shuffled with a local seeded RNG, which is the only
source of randomness — seed it for reproducible output.
"""
import random
import numpy as np


def louvain_cluster(matrix, seed=None, resolution=1.0, max_levels=10):
    """Returns cluster labels (list of ints, 0..k-1) for the input matrix."""
    A = np.asarray(matrix, dtype=float)
    W = (A + A.T) / 2.0
    np.fill_diagonal(W, 0.0)
    n = len(W)
    if n <= 2 or W.sum() == 0:
        return [0] * n

    rng = random.Random(seed)
    # mapping from original node -> current community label, refined per level
    node_to_final = list(range(n))
    cur_W = W

    for _ in range(max_levels):
        comm, moved = _one_level(cur_W, rng, resolution)
        # Fold this level's assignment into the original-node mapping
        node_to_final = [comm[c] for c in node_to_final]
        if not moved:
            break
        cur_W = _aggregate(cur_W, comm)
        if len(cur_W) == 1:
            break

    unique = sorted(set(node_to_final))
    remap = {old: new for new, old in enumerate(unique)}
    return [remap[c] for c in node_to_final]


def _one_level(W, rng, resolution):
    """Phase 1: local moves. Returns (community_of_node, any_move_made)."""
    n = len(W)
    m2 = W.sum()                       # = 2m for undirected weight sum
    if m2 == 0:
        return list(range(n)), False
    deg = W.sum(axis=1)
    comm = list(range(n))
    comm_deg = deg.copy()              # total degree per community

    moved_any = False
    for _ in range(n):                 # bounded passes; usually converges fast
        moved = False
        order = list(range(n))
        rng.shuffle(order)
        for v in order:
            cv = comm[v]
            # weights from v to each neighbouring community
            links = {}
            for u in np.nonzero(W[v])[0]:
                links[comm[u]] = links.get(comm[u], 0.0) + W[v, u]
            # remove v from its community
            comm_deg[cv] -= deg[v]
            base = links.get(cv, 0.0)
            best_c, best_gain = cv, 0.0
            for c, l_vc in links.items():
                gain = (l_vc - base) - resolution * deg[v] * (
                    comm_deg[c] - comm_deg[cv]) / m2
                if gain > best_gain + 1e-12:
                    best_gain, best_c = gain, c
            comm[v] = best_c
            comm_deg[best_c] += deg[v]
            if best_c != cv:
                moved = moved_any = True
        if not moved:
            break

    # compact labels 0..k-1
    unique = sorted(set(comm))
    remap = {old: new for new, old in enumerate(unique)}
    return [remap[c] for c in comm], moved_any


def _aggregate(W, comm):
    """Phase 2: build the community super-graph."""
    k = max(comm) + 1
    agg = np.zeros((k, k))
    n = len(W)
    for i in range(n):
        for j in range(n):
            if W[i, j] > 0:
                agg[comm[i], comm[j]] += W[i, j]
    return agg
