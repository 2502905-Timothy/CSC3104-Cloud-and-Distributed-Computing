
import csv
from pathlib import Path

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)

from shared.model import (
    create_vectorizer,
    create_model,
    train_model,
    predict_messages,
)


def load_dataset():
    dataset_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "sample_messages.csv"
    )

    messages = []
    labels = []

    with open(dataset_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            messages.append(row["message"])
            labels.append(int(row["label"]))

    return messages, labels


def main():
    messages, labels = load_dataset()

    X_train_text, X_test_text, y_train, y_test = train_test_split(
        messages,
        labels,
        test_size=0.3,
        random_state=42,
        stratify=labels,
    )

    # Fit vocabulary using training messages only.
    vectorizer = create_vectorizer()
    X_train = vectorizer.fit_transform(X_train_text)
    X_test = vectorizer.transform(X_test_text)

    model = create_model()
    train_model(model, X_train, y_train)

    predictions = predict_messages(model, X_test)

    print("=== TrustFed Centralised Baseline ===")
    print(f"Training samples: {len(y_train)}")
    print(f"Testing samples: {len(y_test)}")
    print(f"Accuracy:  {accuracy_score(y_test, predictions):.4f}")
    print(f"Precision: {precision_score(y_test, predictions, zero_division=0):.4f}")
    print(f"Recall:    {recall_score(y_test, predictions, zero_division=0):.4f}")
    print(f"F1-score:  {f1_score(y_test, predictions, zero_division=0):.4f}")


if __name__ == "__main__":
    main()
