#!/usr/bin/env python3
"""
DSM Optimizer - CLI
Usage:
    python main.py input.xlsx
    python main.py input.xlsm --sheet 1 --min-cluster 3 --max-k 8
    python main.py input.csv --output result.xlsx --no-plot
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use('Agg')

from dsm_optimizer import DSMOptimizer, DSMConstraints
from dsm_optimizer.io.reader import read_dsm
from dsm_optimizer.io.writer import write_excel
from dsm_optimizer.visualize import plot_dsm, plot_fiedler, plot_pareto


def main():
    p = argparse.ArgumentParser(description='DSM Optimizer')
    p.add_argument('input', help='Input file (.xlsm / .xlsx / .csv)')
    p.add_argument('--output', '-o', default='optimized_dsm.xlsx')
    p.add_argument('--sheet', default=0)
    p.add_argument('--min-cluster', type=int, default=2)
    p.add_argument('--max-cluster', type=int, default=20)
    p.add_argument('--min-k', type=int, default=2)
    p.add_argument('--max-k', type=int, default=10)
    p.add_argument('--bus-threshold', type=float, default=None,
                    help='Fixed connectivity fraction for bus detection. '
                         'Omit for adaptive (statistical outlier) detection.')
    p.add_argument('--seed', type=int, default=None,
                    help='Seed for the sequencing step, for reproducible output.')
    p.add_argument('--type', choices=['component', 'process'], default='component',
                    help='component: cluster into modules (default). '
                         'process: partition/sequence tasks, find loops, suggest tears.')
    p.add_argument('--no-plot', action='store_true')
    p.add_argument('--pareto', action='store_true', help='Run Pareto sweep')
    args = p.parse_args()

    matrix, labels = read_dsm(args.input, args.sheet)
    print(f"Loaded: {len(labels)} elements from {args.input}")

    constraints = DSMConstraints(
        min_cluster_size=args.min_cluster,
        max_cluster_size=args.max_cluster,
        min_clusters=args.min_k,
        max_clusters=args.max_k,
        bus_threshold=args.bus_threshold,
        seed=args.seed,
    )

    if args.type == 'process':
        from dsm_optimizer.algorithms.partitioning import partition_dsm
        result = partition_dsm(matrix, labels, seed=args.seed)
        m = result['metrics']
        print(f"Partitioned: {m['n_blocks']} blocks, {m['n_loops']} loops, "
              f"feedback {m['feedback_before']} -> {m['feedback_after']}")
        for i, lp in enumerate(result['loops']):
            print(f"  Loop {i+1} ({lp['size']} tasks): {', '.join(lp['member_labels'])}")
            for t in lp['tears'][:3]:
                res = 'breaks loop' if t['fully_resolves'] else f"largest left: {t['largest_loop_after']}"
                print(f"    tear {t['from_label']} -> {t['to_label']} "
                      f"(w={t['weight']:g}, frees {t['impact']}, {res})")
    else:
        opt = DSMOptimizer(constraints)
        result = opt.run(matrix, labels)

    write_excel(args.output, result['matrix'], result['labels'], result['clusters'])
    print(f"\nSaved: {args.output}")

    if not args.no_plot:
        base = os.path.splitext(args.output)[0]
        import matplotlib.pyplot as plt

        fig = plot_dsm(matrix, labels, title="Original DSM")
        fig.savefig(f"{base}_original.png", dpi=150, bbox_inches='tight')
        plt.close(fig)

        fig = plot_dsm(result['matrix'], result['labels'], result['clusters'],
                       title="Optimized DSM")
        fig.savefig(f"{base}_optimized.png", dpi=150, bbox_inches='tight')
        plt.close(fig)

        if 'fiedler' in result and len(result['fiedler']) > 1:
            core_labels = [labels[i] for i in range(len(result['fiedler']))]
            fig = plot_fiedler(result['fiedler'], core_labels)
            fig.savefig(f"{base}_fiedler.png", dpi=150, bbox_inches='tight')
            plt.close(fig)

        print(f"Plots saved: {base}_*.png")

    if args.pareto:
        import matplotlib.pyplot as plt
        results = opt.pareto_sweep(matrix)
        base = os.path.splitext(args.output)[0]
        fig = plot_pareto(results)
        fig.savefig(f"{base}_pareto.png", dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"Pareto plot saved.")


if __name__ == '__main__':
    main()
