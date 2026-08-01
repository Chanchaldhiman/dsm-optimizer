from dataclasses import dataclass
from typing import Optional


@dataclass
class DSMConstraints:
    min_cluster_size: int = 2
    max_cluster_size: int = 20
    min_clusters: int = 2
    max_clusters: int = 10

    # fraction of elements connected = bus. Leave as None for adaptive
    # detection (statistical outliers in the connectivity distribution,
    # robust to sparse vs. dense matrices). Set a float in (0, 1] to force
    # a fixed cutoff instead.
    bus_threshold: Optional[float] = None

    # Max allowed inter-cluster mark ratio before the result is flagged as
    # a warning in the output (does not change clustering, purely advisory -
    # see metrics['exceeds_target'] in the pipeline result).
    max_external_ratio: float = 0.30

    # Seed for the simulated-annealing sequencing step. None = non-deterministic
    # (fresh randomness each run). Set an int for reproducible output.
    seed: Optional[int] = None
