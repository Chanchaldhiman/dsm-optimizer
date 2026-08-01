import numpy as np
from sklearn.cluster import KMeans


def spectral_cluster(matrix, k=None, min_k=2, max_k=10, seed=42):
    """
    Spectral clustering on DSM adjacency matrix.
    Returns: (cluster_labels, eigenvalues, fiedler_vector)
    """
    A = (matrix + matrix.T) / 2.0
    np.fill_diagonal(A, 0)
    A = A.astype(float)
    n = len(A)

    min_k = max(2, min(min_k, n - 1))
    max_k = max(min_k, min(max_k, n - 1))

    # Normalized Laplacian: L = I - D^(-1/2) * A * D^(-1/2)
    deg = A.sum(axis=1)
    D_inv_sqrt = np.diag(1.0 / np.sqrt(np.maximum(deg, 1e-10)))
    L_norm = np.eye(n) - D_inv_sqrt @ A @ D_inv_sqrt

    eigenvalues, eigenvectors = np.linalg.eigh(L_norm)

    if k is None:
        k = _eigengap_k(eigenvalues, min_k, max_k)

    k = max(min_k, min(k, max_k))

    features = eigenvectors[:, :k]
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    norms[norms == 0] = 1
    features /= norms

    km = KMeans(n_clusters=k, n_init=20, random_state=seed)
    labels = km.fit_predict(features).tolist()

    fiedler = eigenvectors[:, 1].copy()

    # Orient so the group with greater total squared magnitude is positive.
    # This is more robust than count-based orientation for sparse/asymmetric DSMs
    # where many elements cluster near zero (disconnected or weakly connected nodes).
    # Using sum-of-squares avoids flip failures caused by zero-valued entries.
    pos_energy = np.sum(fiedler[fiedler > 0] ** 2)
    neg_energy = np.sum(fiedler[fiedler < 0] ** 2)
    if neg_energy > pos_energy:
        fiedler = -fiedler

    return labels, eigenvalues, fiedler


def _eigengap_k(eigenvalues, min_k, max_k):
    """Largest eigengap heuristic, clamped to [min_k, max_k]."""
    vals = eigenvalues[1: max_k + 2]
    if len(vals) < 2:
        return min_k
    gaps = np.diff(vals)
    k = int(np.argmax(gaps) + 2)
    return max(min_k, min(k, max_k))


def fiedler_vector(matrix):
    """
    Second-smallest eigenvector of the normalized Laplacian of a (sub)matrix.
    Meaningful only for a CONNECTED graph - on a disconnected one the second
    eigenvalue is still 0 and the "Fiedler" vector degenerates into a
    component indicator (callers should split into components first).
    """
    A = (np.asarray(matrix, dtype=float) + np.asarray(matrix, dtype=float).T) / 2.0
    np.fill_diagonal(A, 0)
    n = len(A)
    if n < 2:
        return np.zeros(n)
    deg = A.sum(axis=1)
    D_inv_sqrt = np.diag(1.0 / np.sqrt(np.maximum(deg, 1e-10)))
    L = np.eye(n) - D_inv_sqrt @ A @ D_inv_sqrt
    _, vecs = np.linalg.eigh(L)
    f = vecs[:, 1].copy()
    pos = np.sum(f[f > 0] ** 2)
    neg = np.sum(f[f < 0] ** 2)
    if neg > pos:
        f = -f
    return f


def connected_components(matrix):
    """Connected components of the symmetrized graph. Returns list of
    index lists, sorted largest first."""
    A = np.asarray(matrix, dtype=float)
    sym = ((A + A.T) > 0)
    n = len(A)
    seen = [False] * n
    comps = []
    for start in range(n):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        comp = []
        while stack:
            v = stack.pop()
            comp.append(v)
            for u in np.nonzero(sym[v])[0]:
                if not seen[u]:
                    seen[u] = True
                    stack.append(int(u))
        comps.append(sorted(comp))
    comps.sort(key=len, reverse=True)
    return comps
