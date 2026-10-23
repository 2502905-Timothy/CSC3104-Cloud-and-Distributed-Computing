
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier


def create_vectorizer():
    """Create the text feature extractor."""
    return TfidfVectorizer(
        lowercase=True,
        max_features=5000,
        ngram_range=(1, 2)
    )


def create_model():
    """Create a classifier suitable for incremental training."""
    return SGDClassifier(
        loss="log_loss",
        max_iter=1000,
        tol=1e-3,
        random_state=42
    )


def train_model(model, X_train, y_train):
    """Train the classifier using labelled examples."""
    model.fit(X_train, y_train)
    return model


def predict_messages(model, X_test):
    """Return predicted class labels."""
    return model.predict(X_test)
