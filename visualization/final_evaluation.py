"""Read-only evaluation of the final federated logistic regression model.

Matches the clients' shared HashingVectorizer and decision threshold exactly.
No training or mutation of the published parameters takes place here.
"""

import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from shared.fed_params import make_vectorizer, unflatten


def evaluate_final_model(parameters: list[float], texts: list[str], labels: list[int]) -> dict:
    if not texts or len(texts) != len(labels):
        raise ValueError("Evaluation dataset must contain labelled messages")
    if not set(labels).issubset({0, 1}):
        raise ValueError("Evaluation labels must be 0 or 1")

    coef, intercept = unflatten(parameters)
    if not np.isfinite(coef).all() or not np.isfinite(intercept).all():
        raise ValueError("Global model contains non-finite parameters")

    features = make_vectorizer().transform(texts)
    predictions = ((features @ coef.T).ravel() + intercept[0] > 0).astype(int)

    return {
        "sample_count": len(labels),
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
    }
