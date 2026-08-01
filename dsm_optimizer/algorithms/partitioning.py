"""
Process-DSM partitioning (sequencing) and tearing analysis.

Convention (same as the rest of the codebase): matrix[i][j] > 0 means row i
DEPENDS ON column j - i needs j's output, so j should come earlier. Under a
given ordering, marks ABOVE the diagonal are feedback (a task depending on
one that hasn't happened yet).

Pipeline for a process/task DSM:
  1. Tarjan's algorithm finds strongly-connected components (SCCs) - the
     iteration loops that no reordering can remove.
  2. The SCC condensation is a DAG; topological ordering (Kahn) gives a
     sequence in which every remaining dependency points backward (feed-
     forward). Level numbers identify tasks that can run in parallel.
  3. Within each loop (SCC size > 1), simulated annealing (the existing
     sa_sequence) orders members to minimise residual feedback.
  4. Tearing analysis: for each loop, rank individual dependencies by how
     much removing ("tearing") them would shrink the loop - these are the
     assumptions/decouplings an engineer should consider making explicit.
"""
import numpy as np
from .sequencing import sa_sequence, feedback_marks


# ── Strongly-connected components (Tarjan, iterative - no recursion limit) ──

def tarjan_scc(matrix):
    """
    SCCs of the dependency graph. Edge i -> j iff matrix[i][j] > 0
    (i depends on j). Returns list of components (lists of indices);
    order is reverse-topological per Tarjan, but callers should not rely
    on it - use condensation_order() for sequencing.
    """
    n = len(matrix)
    adj = [[j for j in range(n) if j != i and matrix[i][j] > 0] for i in range(n)]

    index_counter = [0]
    stack, on_stack = [], [False] * n
    index, lowlink = [-1] * n, [0] * n
    sccs = []

    for root in range(n):
        if index[root] != -1:
            continue
        work = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = lowlink[v] = index_counter[0]
                index_counter[0] += 1
                stack.append(v)
                on_stack[v] = True
            recurse = False
            for i in range(pi, len(adj[v])):
                w = adj[v][i]
                if index[w] == -1:
                    work[-1] = (v, i + 1)
                    work.append((w, 0))
                    recurse = True
                    break
                elif on_stack[w]:
                    lowlink[v] = min(lowlink[v], index[w])
            if recurse:
                continue
            if lowlink[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp.append(w)
                    if w == v:
                        break
                sccs.append(sorted(comp))
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[v])
    return sccs


# ── Condensation DAG topological ordering with levels ─────────────────────

def condensation_order(matrix, sccs):
    """
    Kahn topological sort on the SCC condensation. Because i -> j means
    'i depends on j', dependencies must come FIRST: a block is ready when
    every block it depends on has been scheduled.

    Returns (block_order, levels): block_order is a list of SCC indices in
    execution order; levels[b] is the longest-dependency-chain depth of
    block b (blocks sharing a level have no ordering constraint between
    them - they can proceed in parallel).
    """
    n_blocks = len(sccs)
    of_block = {}
    for b, comp in enumerate(sccs):
        for v in comp:
            of_block[v] = b

    # dep_edges[b] = set of blocks that b depends on
    deps = [set() for _ in range(n_blocks)]
    dependents = [set() for _ in range(n_blocks)]
    n = len(matrix)
    for i in range(n):
        for j in range(n):
            if i != j and matrix[i][j] > 0:
                bi, bj = of_block[i], of_block[j]
                if bi != bj:
                    deps[bi].add(bj)
                    dependents[bj].add(bi)

    indeg = [len(d) for d in deps]
    levels = [0] * n_blocks
    ready = sorted([b for b in range(n_blocks) if indeg[b] == 0])
    order = []
    while ready:
        b = ready.pop(0)
        order.append(b)
        for d in sorted(dependents[b]):
            indeg[d] -= 1
            levels[d] = max(levels[d], levels[b] + 1)
            if indeg[d] == 0:
                ready.append(d)
        ready.sort()
    if len(order) != n_blocks:          # can't happen: condensation is a DAG
        order = list(range(n_blocks))
    return order, levels


# ── Tearing analysis ──────────────────────────────────────────────────────

def tearing_suggestions(matrix, scc, max_suggestions=5):
    """
    For one loop (SCC with >1 members): score every internal dependency by
    how much the loop decomposes if that single mark is torn (removed).

    impact = members freed from the largest remaining sub-loop.
    Ranked by impact desc, then by mark weight asc (prefer tearing weak
    dependencies - they're the cheapest assumptions to make explicit).

    Returns list of dicts: {from, to, weight, impact, largest_loop_after,
    fully_resolves} - 'from' depends on 'to' (the mark at [from][to]).
    """
    members = list(scc)
    size = len(members)
    if size <= 1:
        return []
    pos = {g: i for i, g in enumerate(members)}
    sub = matrix[np.ix_(members, members)].copy()

    edges = [(i, j) for i in range(size) for j in range(size)
             if i != j and sub[i, j] > 0]
    results = []
    for (i, j) in edges:
        saved = sub[i, j]
        sub[i, j] = 0
        parts = tarjan_scc(sub)
        largest = max(len(p) for p in parts)
        sub[i, j] = saved
        results.append({
            "from": members[i],
            "to": members[j],
            "weight": float(saved),
            "impact": size - largest,
            "largest_loop_after": largest,
            "fully_resolves": largest == 1,
        })
    results.sort(key=lambda r: (-r["impact"], r["weight"]))
    return results[:max_suggestions]


# ── Full process-DSM partition ────────────────────────────────────────────

def partition_dsm(matrix, labels, seed=None, tear_suggestions=5):
    """
    Complete partitioning of a process/task DSM.

    Returns dict with the final permuted matrix/labels, per-element block
    ids and levels, loop info (each SCC > 1 with its tearing suggestions),
    and feedback-mark metrics before vs after.
    """
    n = len(labels)
    matrix = np.asarray(matrix, dtype=float)
    fb_before = int(np.triu(matrix, k=1).sum())

    sccs = tarjan_scc(matrix)
    block_order, levels = condensation_order(matrix, sccs)

    final_order = []
    blocks_out = []          # per final block: dict(level, members, is_loop)
    loops = []
    for rank, b in enumerate(block_order):
        comp = sccs[b]
        if len(comp) > 1:
            block_seed = None if seed is None else seed + b
            ordered = sa_sequence(matrix, list(comp), seed=block_seed)
            loops.append({
                "block_index": len(blocks_out),
                "members": comp,
                "member_labels": [labels[i] for i in comp],
                "size": len(comp),
                "internal_feedback": feedback_marks(matrix, ordered),
                "tears": tearing_suggestions(matrix, comp,
                                             max_suggestions=tear_suggestions),
            })
        else:
            ordered = list(comp)
        blocks_out.append({
            "level": levels[b],
            "members": ordered,
            "is_loop": len(comp) > 1,
        })
        final_order.extend(ordered)

    final_matrix = matrix[np.ix_(final_order, final_order)]
    final_labels = [labels[i] for i in final_order]
    fb_after = int(np.triu(final_matrix, k=1).sum())

    # Per-element (in final order) block id + level for banded display
    clusters = []
    elem_levels = []
    for bid, blk in enumerate(blocks_out):
        clusters.extend([bid] * len(blk["members"]))
        elem_levels.extend([blk["level"]] * len(blk["members"]))

    # translate loop tear indices to labels for display
    for lp in loops:
        for t in lp["tears"]:
            t["from_label"] = labels[t["from"]]
            t["to_label"] = labels[t["to"]]

    n_coupled = sum(lp["size"] for lp in loops)

    # Symmetry: fraction of dependencies that are reciprocated. Near 1.0 means
    # the matrix is undirected - component/architecture data, for which
    # process partitioning is the wrong analysis (any ordering has identical
    # feedback on a symmetric matrix). Surfaced so the UI can say so.
    nz = (matrix > 0)
    total_marks_nz = int(nz.sum())
    reciprocated = int((nz & nz.T).sum())          # counts both directions
    symmetry_ratio = reciprocated / total_marks_nz if total_marks_nz else 0.0

    return {
        "matrix": final_matrix,
        "labels": final_labels,
        "clusters": clusters,
        "levels": elem_levels,
        "original_order": final_order,
        "blocks": blocks_out,
        "loops": loops,
        "metrics": {
            "n_elements": n,
            "n_blocks": len(blocks_out),
            "n_loops": len(loops),
            "largest_loop": max((lp["size"] for lp in loops), default=1),
            "coupled_elements": n_coupled,
            "sequential_elements": n - n_coupled,
            "n_levels": max(levels) + 1 if levels else 1,
            "feedback_before": fb_before,
            "feedback_after": fb_after,
            "marks_resolved": fb_before - fb_after,
            "symmetry_ratio": symmetry_ratio,
        },
    }
