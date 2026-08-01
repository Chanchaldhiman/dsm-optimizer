"""
Flask's jsonify() (and the stdlib json module) doesn't know how to serialize
numpy scalar types (np.float64, np.int64, np.bool_) or numpy arrays - every
metric coming out of the pipeline is one of these, so without this helper
the API would throw a TypeError on the very first successful run.
"""
import numpy as np


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return f if np.isfinite(f) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj
