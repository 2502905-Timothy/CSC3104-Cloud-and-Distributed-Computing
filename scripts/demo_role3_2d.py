
"""Local HTTP demonstration of Role 3 model publication with 3 mock clients.

Restart Uvicorn with TRUSTFED_MOCK_AGGREGATION=1 before each run.
"""

import argparse

import requests


def check(response, expected=200):
    if response.status_code != expected:
        raise RuntimeError(
            f"HTTP {response.status_code} (expected {expected}): {response.text}\n"
            "Restart the development Uvicorn server to clear a previous round."
        )
    return response.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-skipped", action="store_true")
    args = parser.parse_args()
    base = "http://127.0.0.1:8000"

    print("Health:", check(requests.get(f"{base}/health")))
    for client in ("demo-a", "demo-b", "demo-c"):
        print("Registered:", check(
            requests.post(f"{base}/clients/register", json={"client_id": client}), 201
        ))

    round_info = check(
        requests.post(f"{base}/rounds/start", json={"deadline_seconds": 120}), 201
    )
    print("Round started:", round_info)
    for name, value in (("demo-a", 1.0), ("demo-b", 2.0), ("demo-c", 3.0)):
        print("Submitted:", check(requests.post(f"{base}/updates", json={
            "client_id": name,
            "round_id": round_info["round_id"],
            "model_version": round_info["model_version"],
            "sample_count": 10,
            "parameters": [value, value, value],
        }), 202))

    print("Closed:", check(requests.post(f"{base}/rounds/close")))
    finalized = check(requests.post(f"{base}/rounds/finalize"))
    print("Finalized:", finalized)
    model = check(requests.get(f"{base}/model/current"))
    print("Global model:", model)

    if args.expect_skipped:
        assert finalized["status"] == "skipped_insufficient_updates"
        assert model == {"model_version": 0, "parameters": [0.0, 0.0, 0.0]}
    else:
        assert finalized["status"] == "completed"
        assert model == {"model_version": 1, "parameters": [2.0, 2.0, 2.0]}
    print("\nPASS: coordinator preserved the required model-version behaviour")


if __name__ == "__main__":
    main()
