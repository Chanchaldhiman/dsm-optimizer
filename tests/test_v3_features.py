"""
Tests for the v3 feature set: partitioning/tearing, Thebeau clustering,
Louvain, stability analysis, and the extended 4-candidate pipeline.
Run with: pytest -v
"""
import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsm_optimizer import DSMOptimizer, DSMConstraints
from dsm_optimizer.algorithms.partitioning import (
    tarjan_scc, condensation_order, tearing_suggestions, partition_dsm)
from dsm_optimizer.algorithms.thebeau import thebeau_cluster
from dsm_optimizer.algorithms.louvain import louvain_cluster
from dsm_optimizer.analysis.stability import stability_analysis
from dsm_optimizer.scoring.thebeau_cost import thebeau_cost


def _block_dsm(n_blocks=4, block=5, p_in=0.8, noise=6, seed=0):
    rng = np.random.RandomState(seed)
    n = n_blocks * block
    m = np.zeros((n, n))
    for b in range(n_blocks):
        for i in range(b * block, (b + 1) * block):
            for j in range(b * block, (b + 1) * block):
                if i != j and rng.rand() < p_in:
                    m[i, j] = 1
    for _ in range(noise):
        i, j = rng.randint(0, n, 2)
        if i != j and i // block != j // block:
            m[i, j] = 1
    return m


def _recovers_blocks(clusters, n_blocks=4, block=5, tol=4):
    ok = 0
    for b in range(n_blocks):
        ids = [clusters[i] for i in range(b * block, (b + 1) * block)]
        if max(ids.count(x) for x in set(ids)) >= tol:
            ok += 1
    return ok


# ── Partitioning ─────────────────────────────────────────────────────────────

def _loop_process():
    labels = list("ABCDEFG")
    m = np.zeros((7, 7))
    m[0, 1] = 1; m[1, 2] = 1; m[2, 0] = 1     # A,B,C loop
    m[3, 2] = 1                                # D depends on C
    m[5, 6] = 1                                # F depends on G
    return m, labels


def test_tarjan_finds_the_loop():
    m, _ = _loop_process()
    sccs = sorted(tuple(s) for s in tarjan_scc(m))
    assert (0, 1, 2) in sccs
    assert all(len(s) == 1 for s in sccs if s != (0, 1, 2))


def test_partition_orders_dependencies_first():
    m, labels = _loop_process()
    r = partition_dsm(m, labels, seed=1)
    pos = {l: i for i, l in enumerate(r["labels"])}
    assert pos["D"] > max(pos["A"], pos["B"], pos["C"])   # D after the loop
    assert pos["G"] < pos["F"]                             # dependency first
    assert r["metrics"]["n_loops"] == 1
    assert r["metrics"]["feedback_after"] <= r["metrics"]["feedback_before"]


def test_partition_acyclic_matrix_has_zero_feedback():
    n = 6
    m = np.zeros((n, n))
    for i in range(1, n):
        m[i, i - 1] = 1            # pure chain, reversed order on purpose
    m = m[::-1, ::-1].copy()       # scramble so original order has feedback
    r = partition_dsm(m, [f"T{i}" for i in range(n)], seed=0)
    assert r["metrics"]["n_loops"] == 0
    assert r["metrics"]["feedback_after"] == 0


def test_tearing_on_two_cycle_fully_resolves():
    m = np.zeros((2, 2)); m[0, 1] = 1; m[1, 0] = 3
    tears = tearing_suggestions(m, [0, 1])
    assert all(t["fully_resolves"] for t in tears)
    # weakest dependency ranked first at equal impact
    assert tears[0]["weight"] == 1


def test_tearing_prefers_high_impact():
    # Two 2-cycles bridged into one big SCC: figure-eight A<->B, B<->C
    m = np.zeros((3, 3))
    m[0, 1] = m[1, 0] = 1
    m[1, 2] = m[2, 1] = 1
    sccs = tarjan_scc(m)
    big = max(sccs, key=len)
    tears = tearing_suggestions(m, big)
    assert tears[0]["impact"] >= 1


# ── New clustering algorithms ────────────────────────────────────────────────

def test_thebeau_recovers_block_structure():
    m = _block_dsm()
    cl = thebeau_cluster(m, seed=5)
    assert _recovers_blocks(cl) >= 3


def test_louvain_recovers_block_structure():
    m = _block_dsm()
    cl = louvain_cluster(m, seed=5)
    assert _recovers_blocks(cl) >= 3


def test_new_algorithms_deterministic_with_seed():
    m = _block_dsm(seed=3)
    assert thebeau_cluster(m, seed=9) == thebeau_cluster(m, seed=9)
    assert louvain_cluster(m, seed=9) == louvain_cluster(m, seed=9)


def test_pipeline_exposes_four_candidates():
    m = _block_dsm()
    labels = [f"E{i}" for i in range(len(m))]
    opt = DSMOptimizer(DSMConstraints(seed=42))
    s1 = opt.cluster_stage(m, labels, verbose=False)
    for name in ("spectral", "mcl", "thebeau", "louvain"):
        assert name in s1
    assert s1["recommended"] in ("spectral", "mcl", "thebeau", "louvain")
    # sequencing any available candidate works
    for name in ("spectral", "thebeau", "louvain"):
        if s1[name] is not None:
            r = opt.sequence_stage(m, labels, s1, name, verbose=False)
            assert len(r["labels"]) == len(labels)


# ── Stability ────────────────────────────────────────────────────────────────

def test_stability_clean_structure_is_consistent():
    m = _block_dsm(noise=2)
    ref = [i // 5 for i in range(len(m))]
    for algo in ("spectral", "thebeau", "louvain"):
        s = stability_analysis(m, algo, ref, runs=8)
        assert s["mean_consistency"] > 0.75, algo
        assert s["co_cluster"].shape == (len(m), len(m))
        assert np.allclose(np.diag(s["co_cluster"]), 1.0)


def test_stability_rejects_unknown_algorithm():
    m = _block_dsm()
    with pytest.raises(ValueError):
        stability_analysis(m, "mcl", [0] * len(m), runs=3)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ── v3.1 additions ───────────────────────────────────────────────────────────

def test_symmetry_ratio_detects_undirected_matrix():
    rng = np.random.RandomState(0)
    n = 10
    m = (rng.rand(n, n) < 0.4).astype(float)
    m = np.maximum(m, m.T); np.fill_diagonal(m, 0)
    r = partition_dsm(m, [f"E{i}" for i in range(n)], seed=1)
    assert r["metrics"]["symmetry_ratio"] > 0.95
    # symmetric matrix: feedback invariant under any permutation
    assert r["metrics"]["feedback_before"] == r["metrics"]["feedback_after"]

    chain = np.zeros((4, 4))
    chain[1, 0] = chain[2, 1] = chain[3, 2] = 1
    r2 = partition_dsm(chain, list("ABCD"), seed=1)
    assert r2["metrics"]["symmetry_ratio"] == 0.0


def test_candidates_carry_k_in_range_flag():
    m = _block_dsm()
    labels = [f"E{i}" for i in range(len(m))]
    opt = DSMOptimizer(DSMConstraints(seed=42, min_clusters=2, max_clusters=3))
    s1 = opt.cluster_stage(m, labels, verbose=False)
    for name in ("spectral", "mcl", "thebeau", "louvain"):
        if s1[name] is not None:
            assert "k_in_range" in s1[name]
            assert s1[name]["k_in_range"] == (2 <= s1[name]["n_clusters"] <= 3)


def test_mcl_prefers_k_within_range():
    # 4 planted blocks: MCL's natural granularity is 4. With max_k=10 the
    # in-range pick must be used and flagged in range.
    m = _block_dsm(noise=2)
    labels = [f"E{i}" for i in range(len(m))]
    opt = DSMOptimizer(DSMConstraints(seed=1, min_clusters=2, max_clusters=10))
    s1 = opt.cluster_stage(m, labels, verbose=False)
    assert s1["mcl"] is not None
    assert s1["mcl"]["k_in_range"] is True


def test_louvain_two_disconnected_cliques():
    # Ground truth with a provably correct answer: two disconnected cliques
    # must come back as exactly two communities.
    n = 10
    m = np.zeros((n, n))
    for a in range(5):
        for b in range(5):
            if a != b:
                m[a, b] = 1
                m[a + 5, b + 5] = 1
    cl = louvain_cluster(m, seed=0)
    assert len(set(cl)) == 2
    assert len(set(cl[:5])) == 1 and len(set(cl[5:])) == 1
    assert cl[0] != cl[5]


def test_thebeau_two_disconnected_cliques():
    n = 10
    m = np.zeros((n, n))
    for a in range(5):
        for b in range(5):
            if a != b:
                m[a, b] = 1
                m[a + 5, b + 5] = 1
    cl = thebeau_cluster(m, seed=0)
    first, second = set(cl[:5]), set(cl[5:])
    assert len(first) == 1 and len(second) == 1 and first != second
    # and it must beat the all-singletons start it began from
    assert thebeau_cost(m, cl) < thebeau_cost(m, list(range(n)))


# ── v3.3: disconnected-core handling ─────────────────────────────────────────

def test_disconnected_core_reports_components_and_valid_fiedler():
    from dsm_optimizer.algorithms.spectral import connected_components
    rng = np.random.RandomState(0)
    n = 12
    m = np.zeros((n, n))
    for i in range(10):
        for j in range(10):
            if i != j and rng.rand() < 0.5:
                m[i, j] = 1
    m = np.maximum(m, m.T)
    m[10, 11] = m[11, 10] = 1        # isolated accessory pair
    labels = [f"E{i}" for i in range(n)]

    comps = connected_components(m)
    assert [len(c) for c in comps] == [10, 2]

    opt = DSMOptimizer(DSMConstraints(seed=1, bus_threshold=0.99))
    s1 = opt.cluster_stage(m, labels, verbose=False)
    assert len(s1["core_components"]) == 2
    # fiedler restricted to the largest component and genuinely two-sided there
    f = np.asarray(s1["fiedler"])
    assert len(f) == len(s1["fiedler_idx"]) == 10
    assert (f > 1e-9).sum() >= 2 and (f < -1e-9).sum() >= 2

    # connected matrices keep the old shape: full-core fiedler, one component
    m2 = _block_dsm(noise=12)
    s2 = opt.cluster_stage(m2, [f"E{i}" for i in range(len(m2))], verbose=False)
    assert len(s2["core_components"]) == 1
    assert len(s2["fiedler"]) == len(s2["fiedler_idx"])
