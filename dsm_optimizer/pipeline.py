import numpy as np
from .algorithms.spectral import spectral_cluster, fiedler_vector, connected_components
from .algorithms.mcl import run_mcl
from .algorithms.thebeau import thebeau_cluster
from .algorithms.louvain import louvain_cluster
from .algorithms.sequencing import sa_sequence, feedback_marks
from .scoring.thebeau_cost import thebeau_cost, external_ratio
from .constraints import DSMConstraints


class DSMOptimizer:
    """
    Two-stage DSM optimization.

    Stage 1 - cluster_stage(): bus detection, then spectral clustering and an
    MCL inflation sweep, each independently scored. Returns both candidates
    plus a recommendation (lower Thebeau cost) - but does NOT commit to one.

    Stage 2 - sequence_stage(): takes the user's chosen candidate, enforces
    min/max cluster size constraints, runs simulated-annealing sequencing
    within each cluster, and builds the final permuted matrix + metrics.

    run() chains both stages using the recommended algorithm automatically -
    the original one-shot behaviour, kept for the CLI and batch scripting.
    """

    def __init__(self, constraints=None):
        self.constraints = constraints or DSMConstraints()

    # ── Stage 1: clustering competition ───────────────────────────────────────

    def cluster_stage(self, matrix, labels, verbose=True):
        n = len(labels)
        c = self.constraints
        _log = print if verbose else lambda *a: None

        _log(f"\nDSM Optimizer  |  {n} elements  |  {int(matrix.sum())} marks")
        _log("=" * 55)

        # ── 0. Bus element detection ──────────────────────────────────────────
        bus_idx = self._find_bus_elements(matrix, c.bus_threshold)
        core_idx = [i for i in range(n) if i not in bus_idx]
        if bus_idx:
            _log(f"Bus elements ({len(bus_idx)}): {[labels[i] for i in bus_idx]}")

        core_mat = matrix[np.ix_(core_idx, core_idx)]
        nc = len(core_idx)

        min_k = max(2, min(c.min_clusters, nc - 1))
        max_k = max(min_k, min(c.max_clusters, nc - 1))

        # ── 1. Spectral clustering ────────────────────────────────────────────
        try:
            spec_cl, eigenvalues, fiedler = spectral_cluster(
                core_mat, min_k=min_k, max_k=max_k)
        except Exception as e:
            _log(f"  Spectral fallback ({e})")
            spec_cl = [i * min_k // nc for i in range(nc)]
            fiedler = np.zeros(nc)
            eigenvalues = np.zeros(nc)

        spectral_cost = thebeau_cost(core_mat, spec_cl)
        spectral_ext = external_ratio(core_mat, spec_cl)
        _log(f"[1] Spectral  ->  {len(set(spec_cl))} clusters  "
             f"(cost {spectral_cost:.1f}, external {spectral_ext*100:.1f}%)")

        spec_mat, spec_labels, spec_clusters = self._build_intermediate(
            matrix, labels, spec_cl, core_idx, bus_idx)

        # ── 2. MCL - try multiple inflation values, keep the best valid one ───
        # Prefer partitions inside the requested k range; fall back to the best
        # out-of-range one (flagged) rather than returning nothing - MCL's
        # granularity is inherent to the matrix and can't be dialled directly.
        best_in, best_in_cost = None, float('inf')
        best_any, best_any_cost = None, float('inf')
        for inflation in [1.4, 1.8, 2.2, 3.0, 4.0]:
            try:
                mcl_cl = run_mcl(core_mat, inflation=inflation)
                n_cl = len(set(mcl_cl))
                if n_cl < 2:
                    continue
                cost = thebeau_cost(core_mat, mcl_cl)
                if min_k <= n_cl <= max_k and cost < best_in_cost:
                    best_in, best_in_cost = mcl_cl, cost
                if cost < best_any_cost:
                    best_any, best_any_cost = mcl_cl, cost
            except Exception:
                continue
        best_mcl = best_in if best_in is not None else best_any
        best_mcl_cost = best_in_cost if best_in is not None else best_any_cost

        if best_mcl is not None:
            mcl_ext = external_ratio(core_mat, best_mcl)
            mcl_raw_mat, mcl_raw_labels, mcl_raw_clusters = self._build_intermediate(
                matrix, labels, best_mcl, core_idx, bus_idx)
            _log(f"[2] MCL sweep ->  {len(set(best_mcl))} clusters  "
                 f"(cost {best_mcl_cost:.1f}, external {mcl_ext*100:.1f}%)")
        else:
            mcl_ext = None
            mcl_raw_mat = mcl_raw_labels = mcl_raw_clusters = None
            _log("[2] MCL sweep ->  all attempts degenerate (<min_k), skipped")

        # ── 3. Thebeau stochastic clustering ──────────────────────────────────
        tb_seed = c.seed if c.seed is not None else 0
        try:
            tb_cl = thebeau_cluster(core_mat, seed=tb_seed)
            tb_cost = thebeau_cost(core_mat, tb_cl)
            tb_ext = external_ratio(core_mat, tb_cl)
            tb_mat, tb_labels, tb_clusters = self._build_intermediate(
                matrix, labels, tb_cl, core_idx, bus_idx)
            _log(f"[3] Thebeau   ->  {len(set(tb_cl))} clusters  "
                 f"(cost {tb_cost:.1f}, external {tb_ext*100:.1f}%)")
            thebeau_cand = {
                'k_in_range': min_k <= len(set(tb_cl)) <= max_k,
                'raw_clusters': tb_cl, 'matrix': tb_mat, 'labels': tb_labels,
                'clusters': tb_clusters, 'n_clusters': len(set(tb_cl)),
                'cost': tb_cost, 'external_ratio': tb_ext,
            }
        except Exception as e:
            _log(f"[3] Thebeau   ->  failed ({e})")
            thebeau_cand = None

        # ── 4. Louvain community detection ────────────────────────────────────
        try:
            lv_cl = louvain_cluster(core_mat, seed=tb_seed)
            lv_cost = thebeau_cost(core_mat, lv_cl)
            lv_ext = external_ratio(core_mat, lv_cl)
            lv_mat, lv_labels, lv_clusters = self._build_intermediate(
                matrix, labels, lv_cl, core_idx, bus_idx)
            _log(f"[4] Louvain   ->  {len(set(lv_cl))} clusters  "
                 f"(cost {lv_cost:.1f}, external {lv_ext*100:.1f}%)")
            louvain_cand = {
                'k_in_range': min_k <= len(set(lv_cl)) <= max_k,
                'raw_clusters': lv_cl, 'matrix': lv_mat, 'labels': lv_labels,
                'clusters': lv_clusters, 'n_clusters': len(set(lv_cl)),
                'cost': lv_cost, 'external_ratio': lv_ext,
            }
        except Exception as e:
            _log(f"[4] Louvain   ->  failed ({e})")
            louvain_cand = None

        # ── Connectivity of the core graph ────────────────────────────────────
        # If bus removal (or the data itself) leaves disconnected islands, the
        # global "Fiedler vector" degenerates into a component indicator -
        # mathematically correct, useless as a diagnostic (a couple of bars,
        # everything else zero). The components ARE the first-order natural
        # decomposition; the Fiedler profile is then computed WITHIN the
        # largest component, where it means something.
        components = connected_components(core_mat)
        if len(components) > 1:
            largest = components[0]
            fiedler = fiedler_vector(core_mat[np.ix_(largest, largest)])
            fiedler_idx = largest
        else:
            fiedler_idx = list(range(nc))

        # Recommendation only - the caller (user or run()) decides.
        candidate_costs = {'spectral': spectral_cost}
        if best_mcl is not None:
            candidate_costs['mcl'] = best_mcl_cost
        if thebeau_cand is not None:
            candidate_costs['thebeau'] = thebeau_cand['cost']
        if louvain_cand is not None:
            candidate_costs['louvain'] = louvain_cand['cost']
        recommended = min(candidate_costs, key=candidate_costs.get)
        _log(f"    Recommended (lower cost): {recommended}")

        return {
            'core_idx': core_idx,
            'bus_elements': bus_idx,
            'min_k': min_k,
            'max_k': max_k,
            'fiedler': fiedler,
            'fiedler_idx': fiedler_idx,
            'core_components': components,
            'eigenvalues': eigenvalues,
            'recommended': recommended,
            'spectral': {
                'k_in_range': min_k <= len(set(spec_cl)) <= max_k,
                'raw_clusters': spec_cl,          # core-index space, for stage 2
                'matrix': spec_mat,               # full reordered view, for display
                'labels': spec_labels,
                'clusters': spec_clusters,
                'n_clusters': len(set(spec_cl)),
                'cost': spectral_cost,
                'external_ratio': spectral_ext,
            },
            'mcl': ({
                'k_in_range': min_k <= len(set(best_mcl)) <= max_k,
                'raw_clusters': best_mcl,
                'matrix': mcl_raw_mat,
                'labels': mcl_raw_labels,
                'clusters': mcl_raw_clusters,
                'n_clusters': len(set(best_mcl)),
                'cost': best_mcl_cost,
                'external_ratio': mcl_ext,
            } if best_mcl is not None else None),
            'thebeau': thebeau_cand,
            'louvain': louvain_cand,
        }

    # ── Stage 2: constraints + SA sequencing on the chosen candidate ─────────

    def sequence_stage(self, matrix, labels, stage1, algorithm, verbose=True):
        """
        algorithm: 'spectral' or 'mcl' - which stage-1 candidate to carry
        forward. Raises ValueError if 'mcl' is requested but stage 1 found
        no valid MCL partition.
        """
        c = self.constraints
        _log = print if verbose else lambda *a: None

        if algorithm not in ('spectral', 'mcl', 'thebeau', 'louvain'):
            raise ValueError(f"Unknown algorithm '{algorithm}'.")
        candidate = stage1.get(algorithm)
        if candidate is None:
            raise ValueError(
                f"No valid {algorithm} partition was found in stage 1 - "
                "pick one of the candidates that produced a result.")

        core_idx = stage1['core_idx']
        bus_idx = stage1['bus_elements']
        min_k = stage1['min_k']
        max_k = stage1['max_k']
        core_mat = matrix[np.ix_(core_idx, core_idx)]
        clusters = list(candidate['raw_clusters'])
        fiedler = stage1['fiedler']

        chosen_info = {
            'algorithm': algorithm,
            'recommended': stage1['recommended'],
            'candidate_costs': {
                name: (stage1[name]['cost'] if stage1.get(name) else None)
                for name in ('spectral', 'mcl', 'thebeau', 'louvain')
            },
            # kept for backward compatibility with older consumers
            'spectral_cost': stage1['spectral']['cost'],
            'mcl_cost': stage1['mcl']['cost'] if stage1['mcl'] else None,
            'mcl_available': stage1['mcl'] is not None,
        }

        # ── Enforce size limits AND the k range on the chosen candidate ───────
        # The k range applies to EVERY algorithm here, not just the ones that
        # can be dialled directly: Thebeau/Louvain find their natural
        # granularity, so a partition outside [min_k, max_k] is merged down /
        # split up at this stage - which is exactly what the UI promises.
        # Crucially, the user's chosen algorithm is PRESERVED: an earlier
        # version silently substituted spectral when a candidate collapsed
        # below min_k, so "sequence MCL" could return spectral's answer.
        clusters = self._enforce_min_size(clusters, core_mat, c)
        clusters = self._enforce_max_size(clusters, core_mat, c)
        clusters, k_merges = self._merge_to_max_k(clusters, core_mat, max_k,
                                                  c.max_cluster_size)
        clusters, k_splits = self._split_to_min_k(clusters, core_mat, min_k,
                                                  c.min_cluster_size)
        chosen_info['k_enforcement'] = {'merges': k_merges, 'splits': k_splits}
        if k_merges or k_splits:
            _log(f"    k-range enforcement: {k_merges} merge(s), {k_splits} split(s)")
        _log(f"    After constraints: {len(set(clusters))} clusters")

        winner_mat, winner_labels, winner_clusters = self._build_intermediate(
            matrix, labels, clusters, core_idx, bus_idx)

        # ── 3. SA sequencing within each cluster ──────────────────────────────
        unique_cl = sorted(set(clusters))
        sequenced = []
        fb_before_total = 0
        fb_after_total = 0
        clusters_changed = 0
        for cid in unique_cl:
            local = [i for i, cl in enumerate(clusters) if cl == cid]
            cluster_seed = None if c.seed is None else c.seed + cid

            fb_before = feedback_marks(core_mat, local)
            reordered = sa_sequence(core_mat, local, seed=cluster_seed)
            fb_after = feedback_marks(core_mat, reordered)

            fb_before_total += fb_before
            fb_after_total += fb_after
            if reordered != local:
                clusters_changed += 1

            sequenced.append([core_idx[i] for i in reordered])

        _log(f"[3] Sequencing  ->  feedback marks {fb_before_total} -> {fb_after_total}  "
             f"({clusters_changed}/{len(unique_cl)} clusters reordered)")

        sequencing_info = {
            'feedback_before': fb_before_total,
            'feedback_after': fb_after_total,
            'marks_resolved': fb_before_total - fb_after_total,
            'clusters_reordered': clusters_changed,
            'total_clusters': len(unique_cl),
            'had_no_feedback_to_resolve': fb_before_total == 0,
        }

        # Bus elements appended as individual groups at end
        for b in bus_idx:
            sequenced.append([b])

        # ── Build final permutation ───────────────────────────────────────────
        final_order = [e for grp in sequenced for e in grp]
        final_matrix = matrix[np.ix_(final_order, final_order)]
        final_labels = [labels[i] for i in final_order]

        final_clusters = []
        for cid, grp in enumerate(sequenced):
            final_clusters.extend([cid] * len(grp))

        # ── Metrics ───────────────────────────────────────────────────────────
        metrics = self._metrics(final_matrix, final_clusters, n_bus=len(bus_idx))
        metrics['exceeds_target'] = metrics['external_ratio'] > c.max_external_ratio
        _log(f"\n  Clusters : {metrics['n_clusters']}")
        _log(f"  External : {metrics['external_ratio']*100:.1f}%")
        _log(f"  Cost     : {metrics['cost']:.2f}")
        if metrics['exceeds_target']:
            _log(f"  ⚠ External coupling ({metrics['external_ratio']*100:.1f}%) exceeds "
                 f"target ({c.max_external_ratio*100:.0f}%) - this partition may need "
                 f"manual review. Try widening --min-k/--max-k or adjusting cluster size limits.")

        return {
            'matrix': final_matrix,
            'labels': final_labels,
            'clusters': final_clusters,
            'original_order': final_order,
            'metrics': metrics,
            'winner': chosen_info,
            'after_constraints': {
                'matrix': winner_mat,
                'labels': winner_labels,
                'clusters': winner_clusters,
                'n_clusters': len(set(clusters)),
            },
            'sequencing': sequencing_info,
            'fiedler': fiedler,
        }

    # ── One-shot wrapper (CLI / batch): auto-picks the recommendation ────────

    def run(self, matrix, labels, verbose=True):
        stage1 = self.cluster_stage(matrix, labels, verbose=verbose)
        result = self.sequence_stage(matrix, labels, stage1,
                                     stage1['recommended'], verbose=verbose)

        # Keep the original run() result shape intact for CLI / tests.
        result['after_spectral'] = {
            k: v for k, v in stage1['spectral'].items() if k != 'raw_clusters'
        }
        result['after_mcl'] = (
            {k: v for k, v in stage1['mcl'].items() if k != 'raw_clusters'}
            if stage1['mcl'] else None
        )
        result['eigenvalues'] = stage1['eigenvalues']
        result['bus_elements'] = stage1['bus_elements']
        return result

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_intermediate(self, matrix, labels, clusters, core_idx, bus_idx):
        """
        Reorder matrix by cluster assignment (no SA sequencing).
        Returns (reordered_matrix, reordered_labels, cluster_ids) for plotting.
        """
        unique_cl = sorted(set(clusters))
        ordered_core = []
        out_clusters = []
        for cid in unique_cl:
            members = [i for i, cl in enumerate(clusters) if cl == cid]
            ordered_core.extend(members)
            out_clusters.extend([cid] * len(members))

        ordered_full = [core_idx[i] for i in ordered_core] + list(bus_idx)
        n_core_clusters = len(unique_cl)
        out_clusters += [n_core_clusters + i for i in range(len(bus_idx))]

        reordered_matrix = matrix[np.ix_(ordered_full, ordered_full)]
        reordered_labels = [labels[i] for i in ordered_full]
        return reordered_matrix, reordered_labels, out_clusters

    def _find_bus_elements(self, matrix, threshold):
        """
        Bus elements connect to an unusually large fraction of the rest of
        the system (data/power buses, shared infrastructure, etc.).

        threshold=None (default): adaptive. Flags statistical outliers in
        the connectivity distribution using a robust z-score (median + MAD),
        so the same logic works whether the DSM is sparse (5% fill) or
        dense (40% fill) without per-project tuning. Floored at 0.15 so a
        roughly uniform matrix with no real hubs isn't over-flagged.

        threshold=float: fixed override, same behaviour as before - flag
        anything above that fraction of connectivity.
        """
        n = len(matrix)
        sym = ((matrix + matrix.T) > 0).astype(float)
        np.fill_diagonal(sym, 0)
        conn = sym.sum(axis=1) / max(n - 1, 1)

        if threshold is None:
            med = np.median(conn)
            mad = np.median(np.abs(conn - med))
            robust_std = mad * 1.4826 if mad > 0 else conn.std()
            threshold = max(med + 3.5 * robust_std, 0.15)

        return [i for i in range(n) if conn[i] > threshold]

    def _merge_to_max_k(self, clusters, matrix, max_k, max_size):
        """
        Merge clusters until at most max_k remain. Each step merges the pair
        with the largest total inter-cluster dependency weight, preferring
        merges that keep the combined size within max_cluster_size (if the
        constraints conflict, max_k wins and the size overage is accepted -
        an explicit user k-limit beats a soft size preference).
        Returns (clusters, n_merges).
        """
        clusters = list(clusters)
        sym = matrix + matrix.T
        merges = 0
        while len(set(clusters)) > max_k:
            ids = sorted(set(clusters))
            members = {cid: [i for i, x in enumerate(clusters) if x == cid]
                       for cid in ids}
            best = None      # ((size_ok, weight), a, b) - tuple compare
            for ai in range(len(ids)):
                for bi in range(ai + 1, len(ids)):
                    a, b = ids[ai], ids[bi]
                    w = float(sum(sym[i, j] for i in members[a]
                                  for j in members[b]))
                    size_ok = (max_size <= 0 or
                               len(members[a]) + len(members[b]) <= max_size)
                    key = (size_ok, w)
                    if best is None or key > best[0]:
                        best = (key, a, b)
            _, a, b = best
            clusters = [a if x == b else x for x in clusters]
            merges += 1
        unique = sorted(set(clusters))
        remap = {old: new for new, old in enumerate(unique)}
        return [remap[x] for x in clusters], merges

    def _split_to_min_k(self, clusters, matrix, min_k, min_size):
        """
        Split clusters until at least min_k exist, preserving whatever
        algorithm produced them. Each step splits the largest splittable
        cluster in two via spectral on its sub-matrix (index-halves
        fallback), preferring clusters big enough that both halves can
        respect min_cluster_size. Stops early if nothing of size >= 2 is
        left to split (min_k was infeasible).
        Returns (clusters, n_splits).
        """
        import math
        clusters = list(clusters)
        splits = 0
        next_id = (max(clusters) + 1) if clusters else 0
        while len(set(clusters)) < min_k:
            counts = {}
            for x in clusters:
                counts[x] = counts.get(x, 0) + 1
            # prefer clusters where both halves can satisfy min_size
            candidates = sorted(counts.items(), key=lambda kv: -kv[1])
            target = None
            for cid, cnt in candidates:
                if cnt >= max(2, 2 * min_size):
                    target = cid
                    break
            if target is None:       # relax: any cluster of >= 2
                for cid, cnt in candidates:
                    if cnt >= 2:
                        target = cid
                        break
            if target is None:
                break                # nothing splittable - infeasible min_k
            members = [i for i, x in enumerate(clusters) if x == target]
            sub = matrix[np.ix_(members, members)]
            try:
                sub_labels, _, _ = spectral_cluster(sub, k=2, min_k=2, max_k=2)
                if len(set(sub_labels)) < 2:
                    raise ValueError("degenerate")
            except Exception:
                half = math.ceil(len(members) / 2)
                sub_labels = [0] * half + [1] * (len(members) - half)
            for local_i, global_i in enumerate(members):
                if sub_labels[local_i] == 1:
                    clusters[global_i] = next_id
            next_id += 1
            splits += 1
        unique = sorted(set(clusters))
        remap = {old: new for new, old in enumerate(unique)}
        return [remap[x] for x in clusters], splits

    def _enforce_min_size(self, clusters, matrix, c):
        """Merge clusters smaller than min_cluster_size into their most-connected large neighbour.
        Runs iteratively until convergence or no large cluster is available."""
        result = list(clusters)

        for _ in range(len(clusters)):   # max passes = n (guaranteed termination)
            counts = {}
            for cl in result:
                counts[cl] = counts.get(cl, 0) + 1

            large = [cl for cl, cnt in counts.items() if cnt >= c.min_cluster_size]
            if not large:
                break  # no cluster meets min size; cannot enforce, return as-is

            changed = False
            new_result = []
            for i, cl in enumerate(result):
                if counts[cl] < c.min_cluster_size:
                    # Find the large cluster most connected to element i
                    el_i = i  # capture for lambda
                    best = max(large, key=lambda lc: sum(
                        matrix[el_i, j] for j, c2 in enumerate(result) if c2 == lc))
                    new_result.append(best)
                    changed = True
                else:
                    new_result.append(cl)
            result = new_result

            if not changed:
                break

        unique = sorted(set(result))
        remap = {old: new for new, old in enumerate(unique)}
        return [remap[cl] for cl in result]

    def _enforce_max_size(self, clusters, matrix, c):
        """
        Split clusters larger than max_cluster_size by re-running spectral
        on each offending cluster's sub-matrix.
        """
        if c.max_cluster_size <= 0:
            return clusters

        result = list(clusters)
        next_id = max(clusters) + 1
        import math

        # Guard: at most n_elements iterations to prevent infinite loops
        max_iters = len(clusters)
        iteration = 0

        changed = True
        while changed and iteration < max_iters:
            changed = False
            iteration += 1
            counts = {}
            for cl in result:
                counts[cl] = counts.get(cl, 0) + 1

            for cl, cnt in sorted(counts.items()):
                if cnt <= c.max_cluster_size:
                    continue
                members = [i for i, c2 in enumerate(result) if c2 == cl]
                sub_mat = matrix[np.ix_(members, members)]
                n_splits = max(2, math.ceil(cnt / c.max_cluster_size))
                try:
                    sub_labels, _, _ = spectral_cluster(
                        sub_mat, k=n_splits, min_k=2, max_k=n_splits)
                    # Validate: spectral must return at least 2 distinct groups.
                    # On dense or uniform sub-matrices it can collapse to 1 cluster.
                    if len(set(sub_labels)) < 2:
                        raise ValueError("degenerate")
                except Exception:
                    # Guaranteed sequential fallback - never raises, always enforces.
                    # Less connectivity-aware than spectral but the constraint is met.
                    sub_labels = [min(i * n_splits // cnt, n_splits - 1)
                                  for i in range(cnt)]

                # Apply the split (sub_label=0 keeps original cluster id; others get new ids)
                for local_i, global_i in enumerate(members):
                    if sub_labels[local_i] > 0:
                        result[global_i] = next_id + sub_labels[local_i] - 1
                next_id += n_splits - 1
                changed = True
                break  # restart while-loop with updated counts

        unique = sorted(set(result))
        remap = {old: new for new, old in enumerate(unique)}
        return [remap[cl] for cl in result]

    def _metrics(self, matrix, clusters, n_bus=0):
        """
        Compute coupling metrics.
        n_bus: number of bus elements at the END of the matrix to exclude.
        Bus elements connect to everything by definition and inflate external ratio
        in a misleading way. All coupling metrics are computed on core elements only.
        n_clusters counts core clusters only (not bus singleton clusters).
        """
        n = len(matrix)
        n_core = n - n_bus

        # Compute on core elements only
        core_mat = matrix[:n_core, :n_core]
        core_cl = clusters[:n_core]

        nc = n_core
        total = core_mat.sum()
        ext = sum(core_mat[i, j] for i in range(nc) for j in range(nc)
                  if i != j and core_cl[i] != core_cl[j] and core_mat[i, j] > 0)
        return {
            'n_clusters': len(set(core_cl)),
            'total_marks': int(matrix.sum()),       # all marks including bus (for display)
            'core_marks': int(total),               # marks among core elements
            'external_marks': int(ext),
            'external_ratio': ext / max(total, 1),
            'cost': thebeau_cost(core_mat, core_cl),
        }

    def pareto_sweep(self, matrix, k_range=None):
        """Run spectral at each k; return list of (k, ext_ratio, cost)."""
        if k_range is None:
            k_range = range(2, min(12, len(matrix)))
        results = []
        for k in k_range:
            try:
                cl, _, _ = spectral_cluster(matrix, k=k, min_k=k, max_k=k)
                m = self._metrics(matrix, cl)
                results.append((k, m['external_ratio'], m['cost']))
            except Exception:
                pass
        return results
