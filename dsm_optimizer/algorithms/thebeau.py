"""
Thebeau's stochastic clustering algorithm (Thebeau 2001, "Knowledge flow
through effective use of DSMs" - the algorithm whose coordination-cost
objective this project already uses for scoring).

Faithful to the published pseudocode: elements start in singleton clusters;
random elements receive 'bids' from every cluster (strong-interaction
clusters bid high, large clusters are penalised); moves that reduce total
coordination cost are accepted, with occasional random acceptance of
worse moves (rand_accept) and occasional second-best bids (rand_bid) to
escape local minima. Empty clusters are deleted at the end.

Seedable via a local RNG - never touches global random state.
"""
import random
import numpy as np
from ..scoring.thebeau_cost import thebeau_cost


def thebeau_cluster(matrix, pow_cc=1.0, pow_bid=1.0, pow_dep=4.0,
                    times=2, stable_limit=2, seed=None):
    """
    Returns cluster labels (list of ints, 0..k-1).

    times: element-pick passes per stability check = times * n picks.
    stable_limit: consecutive no-improvement passes before stopping.
    rand_accept / rand_bid follow Thebeau's 1-in-2n convention.
    """
    A = np.asarray(matrix, dtype=float)
    n = len(A)
    if n <= 2:
        return [0] * n

    rng = random.Random(seed)
    sym = A + A.T                      # bids consider both directions
    np.fill_diagonal(sym, 0)

    clusters = list(range(n))          # start: each element its own cluster
    cur_cost = thebeau_cost(A, clusters)
    best_cost = cur_cost
    best_clusters = clusters[:]

    rand_accept = 2 * n
    rand_bid = 2 * n
    stable = 0
    max_system_passes = 40             # hard cap for pathological matrices

    for _ in range(max_system_passes):
        improved_this_pass = False
        for _ in range(times * n):
            e = rng.randrange(n)

            # Bid from every existing cluster
            ids = sorted(set(clusters))
            bids = []
            for cid in ids:
                members = [i for i, c in enumerate(clusters) if c == cid and i != e]
                if not members:
                    bids.append((0.0, cid))
                    continue
                inter = sum(sym[e, m] for m in members)
                bid = (inter ** pow_dep) / (len(members) ** pow_bid) if inter > 0 else 0.0
                bids.append((bid, cid))
            bids.sort(reverse=True)
            if bids[0][0] <= 0:
                continue

            # Occasionally take the second-best bid
            pick = 0
            if len(bids) > 1 and bids[1][0] > 0 and rng.randrange(rand_bid) == 0:
                pick = 1
            target = bids[pick][1]
            if target == clusters[e]:
                continue

            old = clusters[e]
            clusters[e] = target
            new_cost = thebeau_cost(A, clusters)
            # Thebeau's published flow: accept against the CURRENT cost.
            # (An earlier version compared against the global best, which
            # strands the search: once best is low, every exploratory step
            # is rejected and legitimate downhill moves from the current
            # state never happen.)
            if new_cost <= cur_cost or rng.randrange(rand_accept) == 0:
                cur_cost = new_cost
                if new_cost < best_cost:
                    best_cost = new_cost
                    best_clusters = clusters[:]
                    improved_this_pass = True
            else:
                clusters[e] = old
        if improved_this_pass:
            stable = 0
        else:
            stable += 1
            if stable >= stable_limit:
                break

    # Relabel best solution 0..k-1
    unique = sorted(set(best_clusters))
    remap = {old: new for new, old in enumerate(unique)}
    return [remap[c] for c in best_clusters]