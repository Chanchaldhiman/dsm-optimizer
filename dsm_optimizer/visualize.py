import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches


def plot_dsm(matrix, labels, clusters=None, title="DSM", save_path=None):
    n = len(labels)
    img = np.ones((n, n, 3))

    for i in range(n):
        for j in range(n):
            if i == j:
                img[i, j] = [0.75, 0.75, 0.75]
            elif matrix[i, j] > 0:
                if clusters and clusters[i] == clusters[j]:
                    img[i, j] = [0.18, 0.55, 0.90]   # blue = intra
                elif clusters:
                    img[i, j] = [0.95, 0.30, 0.30]   # red = external
                else:
                    img[i, j] = [0.20, 0.20, 0.80]

    size = max(6, n * 0.38)
    fig, ax = plt.subplots(figsize=(size, size))
    ax.imshow(img, aspect='equal', interpolation='none')
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=90, fontsize=max(5, 9 - n // 10))
    ax.set_yticklabels(labels, fontsize=max(5, 9 - n // 10))
    ax.set_title(title, fontsize=11, fontweight='bold', pad=8)

    if clusters:
        _add_cluster_boxes(ax, clusters)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_fiedler(fiedler, labels, save_path=None):
    idx = np.argsort(fiedler)
    sorted_vals = fiedler[idx]
    sorted_labels = [labels[i] for i in idx]
    n = len(labels)

    fig, ax = plt.subplots(figsize=(max(8, n * 0.3), 5))

    colors = ['#1D4ED8' if v >= 0 else '#DC2626' for v in sorted_vals]
    bars = ax.bar(range(n), sorted_vals, color=colors, alpha=0.88,
                  edgecolor='white', linewidth=0.6)

    ax.axhline(0, color='#111827', linewidth=1.2)

    # Shade the two regions and label them
    pos_indices = [i for i, v in enumerate(sorted_vals) if v >= 0]
    neg_indices = [i for i, v in enumerate(sorted_vals) if v < 0]

    if neg_indices:
        ax.axvspan(min(neg_indices) - 0.5, max(neg_indices) + 0.5,
                   alpha=0.06, color='#DC2626', zorder=0)
        ax.text((min(neg_indices) + max(neg_indices)) / 2, ax.get_ylim()[0] * 0.85,
                'Cluster A', ha='center', fontsize=9, color='#DC2626', fontweight='600')
    if pos_indices:
        ax.axvspan(min(pos_indices) - 0.5, max(pos_indices) + 0.5,
                   alpha=0.06, color='#1D4ED8', zorder=0)
        ax.text((min(pos_indices) + max(pos_indices)) / 2, ax.get_ylim()[0] * 0.85,
                'Cluster B', ha='center', fontsize=9, color='#1D4ED8', fontweight='600')

    ax.set_xticks(range(n))
    ax.set_xticklabels(sorted_labels, rotation=90, fontsize=max(6, 9 - n // 10))
    ax.set_ylabel("Fiedler value", fontsize=10)
    ax.set_title("Fiedler Vector - Natural Primary Decomposition", fontsize=11,
                 fontweight='bold')
    ax.grid(axis='y', alpha=0.25, linestyle='--')

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#1D4ED8', alpha=0.85, label='Cluster B (positive)'),
        Patch(facecolor='#DC2626', alpha=0.85, label='Cluster A (negative)'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=8, framealpha=0.9)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_pareto(results, save_path=None):
    """results: list of (n_clusters, external_ratio, cost)"""
    ks = [r[0] for r in results]
    ext = [r[1] * 100 for r in results]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(ks, ext, 'o-', color='steelblue', markersize=8, linewidth=2)
    for k, e in zip(ks, ext):
        ax.annotate(f'{e:.1f}%', (k, e), textcoords='offset points',
                    xytext=(4, 4), fontsize=8)
    ax.set_xlabel("Number of Clusters (k)")
    ax.set_ylabel("External Interactions (%)")
    ax.set_title("Pareto Front: Modularity vs. Inter-Cluster Coupling", fontweight='bold')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def _add_cluster_boxes(ax, clusters):
    palette = ['#1f77b4', '#2ca02c', '#ff7f0e', '#9467bd',
               '#8c564b', '#e377c2', '#bcbd22', '#17becf']
    for cid in sorted(set(clusters)):
        pos = [i for i, c in enumerate(clusters) if c == cid]
        mn, mx = min(pos), max(pos)
        rect = patches.Rectangle(
            (mn - 0.5, mn - 0.5), mx - mn + 1, mx - mn + 1,
            linewidth=2.2,
            edgecolor=palette[cid % len(palette)],
            facecolor='none', zorder=5
        )
        ax.add_patch(rect)
