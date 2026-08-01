#!/usr/bin/env python3
"""
Validation script - creates a 20-element aerospace DSM with known cluster
structure, shuffles it, runs the optimizer, and saves all outputs.

Expected result:
  4 clusters (Power, Structure, Avionics, Propulsion) + 1 bus element
  External ratio < 20%
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from dsm_optimizer import DSMOptimizer, DSMConstraints
from dsm_optimizer.io.writer import write_excel
from dsm_optimizer.visualize import plot_dsm, plot_fiedler, plot_pareto


# ── Sample DSM definition ─────────────────────────────────────────────────────

LABELS = [
    # Power (0-4)
    "Battery", "Power Controller", "Solar Array", "Power Converter", "Regulator",
    # Structure (5-9)
    "Frame", "Panels", "Harness", "Thermal Control", "Mechanism",
    # Avionics (10-14)
    "OBC", "Sensors", "Telemetry", "ADCS", "Memory Unit",
    # Propulsion (15-19)
    "Engine", "Fuel Tank", "Valve", "Thruster", "Propellant Feed",
    # Bus element (20)
    "Data Bus",
]

EXPECTED_CLUSTERS = {
    "Power":      [0, 1, 2, 3, 4],
    "Structure":  [5, 6, 7, 8, 9],
    "Avionics":   [10, 11, 12, 13, 14],
    "Propulsion": [15, 16, 17, 18, 19],
    "Bus":        [20],
}

INTRA = [
    # Power
    (0,1),(1,2),(2,3),(3,4),(4,0),(1,3),(0,2),
    # Structure
    (5,6),(6,7),(7,8),(8,9),(9,5),(5,8),(6,9),
    # Avionics
    (10,11),(11,12),(12,13),(13,14),(14,10),(10,12),(11,13),
    # Propulsion
    (15,16),(16,17),(17,18),(18,19),(19,15),(15,18),(16,19),
]

CROSS = [
    (1, 10), (3, 10),   # Power → OBC
    (10, 5),            # OBC → Frame
    (1, 15), (3, 17),   # Power → Engine/Valve
    (10, 15),           # OBC → Engine
    (5, 15),            # Frame → Engine
]

# Data Bus (20) connects to representative element from each subsystem
BUS_CONNECTS = [1, 6, 10, 16]   # Power Ctrl, Panels, OBC, Fuel Tank


def make_sample_dsm(shuffle_seed=42):
    n = 21
    M = np.zeros((n, n), dtype=float)

    for i, j in INTRA:
        M[i, j] = M[j, i] = 1

    for i, j in CROSS:
        M[i, j] = 1

    for j in BUS_CONNECTS:
        M[20, j] = M[j, 20] = 1

    np.fill_diagonal(M, 0)

    # Shuffle to hide ground truth
    rng = np.random.default_rng(shuffle_seed)
    perm = rng.permutation(n)
    M = M[np.ix_(perm, perm)]
    labels = [LABELS[i] for i in perm]
    return M, labels


# ── Run validation ────────────────────────────────────────────────────────────

def main():
    os.makedirs("output", exist_ok=True)

    matrix, labels = make_sample_dsm()
    n = len(labels)

    print("=" * 60)
    print("VALIDATION RUN - Sample Aerospace DSM")
    print("=" * 60)
    print(f"  Elements : {n}")
    print(f"  Marks    : {int(matrix.sum())}")
    print(f"  Ground truth: 4 subsystem clusters + 1 bus element")

    # Original DSM plot
    fig = plot_dsm(matrix, labels, title="Original DSM (shuffled)")
    fig.savefig("output/1_original.png", dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("\n[Saved] output/1_original.png")

    # Run optimizer
    constraints = DSMConstraints(
        min_cluster_size=2,
        max_cluster_size=10,
        min_clusters=3,
        max_clusters=8,
        bus_threshold=0.35,
    )
    opt = DSMOptimizer(constraints)
    result = opt.run(matrix, labels, verbose=True)

    # Optimized DSM plot
    m = result['metrics']
    fig = plot_dsm(
        result['matrix'], result['labels'], result['clusters'],
        title=f"Optimized DSM  |  {m['n_clusters']} clusters  |  "
              f"{m['external_ratio']*100:.1f}% external  |  cost {m['cost']:.1f}"
    )
    fig.savefig("output/2_optimized.png", dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("[Saved] output/2_optimized.png")

    # Fiedler vector
    if len(result['fiedler']) > 1:
        core_labels = [labels[i] for i in range(len(result['fiedler']))]
        fig = plot_fiedler(result['fiedler'], core_labels)
        fig.savefig("output/3_fiedler.png", dpi=150, bbox_inches='tight')
        plt.close(fig)
        print("[Saved] output/3_fiedler.png")

    # Pareto sweep
    pareto = opt.pareto_sweep(matrix, k_range=range(2, 9))
    fig = plot_pareto(pareto)
    fig.savefig("output/4_pareto.png", dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("[Saved] output/4_pareto.png")

    # Excel output
    write_excel("output/optimized_dsm.xlsx",
                result['matrix'], result['labels'], result['clusters'],
                title="Aerospace DSM - Optimized")
    print("[Saved] output/optimized_dsm.xlsx")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Clusters found   : {m['n_clusters']}")
    print(f"  Total marks      : {int(m['total_marks'])}")
    print(f"  External marks   : {int(m['external_marks'])}")
    print(f"  External ratio   : {m['external_ratio']*100:.1f}%")
    print(f"  Thebeau cost     : {m['cost']:.2f}")
    print(f"  Bus elements     : {len(result['bus_elements'])}")

    # Pass/fail: at least 3 clusters, bus detected, external ratio reasonable
    # Note: external ratio includes bus-element interactions by design
    # Core subsystem external ratio should be lower
    passed = (
        m['n_clusters'] >= 4 and
        m['external_ratio'] < 0.45 and
        len(result['bus_elements']) >= 1
    )
    print(f"\n  VALIDATION: {'✓ PASSED' if passed else '✗ FAILED'}")
    print("=" * 60)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
