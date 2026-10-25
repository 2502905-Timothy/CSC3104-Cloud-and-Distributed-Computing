# Used as the baseline file to compare against.
# Only math,  no server, no files no database

import numpy as np

def fedavg(updates: dict[str, dict], max_weight_ratio: float | None = None) -> list[float]:
    if not updates:
        raise ValueError("No updates to aggregate")
    
    # Sort client IDs so the result is the same every run
    # Coordinator needs the aggregator to be repeatable in case it retries.
    ids = sorted(updates)
    
    # one weight per client, how many messages it trained on
    weights = np.array([updates[c]["sample_count"] for c in ids], dtype = np.float64)
    
    if max_weight_ratio is not None:
        # np.minimum clips each weight down to the cap; smaller weights are untouched
        weights = np.minimum(weights, max_weight_ratio * np.median(weights))
    # Stack all clients' parameter lists into a table: one row per client
    stacked = np.stack([np.asarray(updates[c]["parameters"], dtype = np.float64) for c in ids])
    
    # Normalise weights so they add up to 1, multiply client row by its weight,
    # then add the rows together (sum down the clients) = weighted average
    return (stacked * (weights/weights.sum())[:, None]).sum(axis=0).tolist()