# TrustFed Coordinator and Client GUIs

`visualization/` provides two browser interfaces to the real TrustFed code:

- **Coordinator GUI** — shows global-model version, round status, accepted/rejected updates, online/dataset-ready clients, sample counts, five-round progress and committed numerical Trust Scores with bars; starts rounds and evaluates the final model.
- **Client GUI** — selects/validates a CSV, registers a unique client ID, sends readiness heartbeats, downloads the global model at each new round, trains and submits updated model parameters, and reports the result of each round.

The GUIs are not fake simulations. The Client GUI uses `client.train.local_train` to train within **the process hosting that GUI**. The distinction is **where that process runs**:

| Mode | Coordinator API | Client GUI and training | Coordinator GUI |
| --- | --- | --- | --- |
| Local development | Python on your computer | Three separate Python processes on your computer | Python on your computer |
| Kubernetes | Coordinator Pod | Three Client GUI processes, one inside each Client Pod | Python on your computer, via port-forward |

In both modes, the raw client CSV is retained in the Client GUI's process. The Coordinator gets readiness reports and model updates, **not raw CSV data**. The Coordinator GUI handles selected final evaluation CSVs locally and downloads the final global model through the API.

## First-time Python setup

Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Every **new terminal** that executes `python` needs to be in the project root with `source .venv/bin/activate` run again. Do not assume the new terminal automatically uses `.venv`.

## Option A — Run everything locally

Start **five terminals** in the project root. Use a fresh SQLite filename if you want a v0 demonstration and want to preserve previous tests.

**Terminal 1 — Coordinator backend:**

```bash
source .venv/bin/activate
mkdir -p "$HOME/.trustfed"
export TRUSTFED_AGGREGATOR=trustfed
export TRUSTFED_DB_PATH="$HOME/.trustfed/trustfed-local-demo.sqlite3"
export TRUSTFED_VALIDATION_PATH=data/coordinator_val_set.csv
python -m uvicorn coordinator.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — Coordinator GUI:**

```bash
source .venv/bin/activate
python -m visualization.app coordinator --port 8500 --coordinator-url http://127.0.0.1:8000
```

**Terminal 3 — Client 1:**

```bash
source .venv/bin/activate
python -m visualization.app client --port 8501
```

**Terminal 4 — Client 2:**

```bash
source .venv/bin/activate
python -m visualization.app client --port 8502
```

**Terminal 5 — Client 3:**

```bash
source .venv/bin/activate
python -m visualization.app client --port 8503
```

Open the Coordinator at http://127.0.0.1:8500 and the clients at http://127.0.0.1:8501, http://127.0.0.1:8502 and http://127.0.0.1:8503. Use IDs `client-1`, `client-2`, `client-3` and upload the matching example CSVs from `data/client_1_train.csv`, `data/client_2_train.csv`, `data/client_3_train.csv`.

Select a CSV and click **Connect** on each client. A newly opened Client GUI shows `OFFLINE` until connected. The Coordinator should display three ready clients after receiving their heartbeats. Start each round from the Coordinator; a successful publication requires **three accepted model updates**. Finish **five successful rounds**, then choose `data/final_test_set.csv` under **Final Model Evaluation** to display accuracy, precision, recall and F1-score for model `v5`.

## Option B — Kubernetes-hosted Client GUIs

For full Docker build, Kubernetes deployment, cleanup, and troubleshooting instructions, see [docs/GUI_KUBERNETES_INTEGRATION.md](../docs/GUI_KUBERNETES_INTEGRATION.md).

**Do not simultaneously run the local backend/Client GUI processes on ports `8000` and `8501`–`8503`** when those ports are needed for Kubernetes port-forwards.

After deploying one Coordinator Pod and three Client Pods, start the following port-forwards **in separate terminals**:

```bash
kubectl port-forward svc/trustfed-coordinator 8000:8000
```

```bash
kubectl port-forward pod/trustfed-clients-0 8501:8501
```

```bash
kubectl port-forward pod/trustfed-clients-1 8502:8501
```

```bash
kubectl port-forward pod/trustfed-clients-2 8503:8501
```

In another terminal, from the project root, launch **only the local Coordinator GUI**:

```bash
source .venv/bin/activate
python -m visualization.app coordinator --port 8500 --coordinator-url http://127.0.0.1:8000
```

The browser addresses remain the same as in local mode, but **each Client GUI is now running inside its respective Kubernetes Pod**, so the uploaded CSV is used for training inside that Pod.

## CSV requirements and training behavior

- CSV header: `text,label` or `message,label`.
- Every nonblank row must contain nonempty text and a label of `0` (legitimate) or `1` (scam).
- Clients validate data before registering; **Connect** starts polling and heartbeats, not an immediate training round.
- When the Coordinator starts a round, each participating client downloads the global model, trains on the selected dataset, and submits updated model parameters and its sample count.
- Readiness is self-reported by clients: a heartbeat is sent approximately every 10 seconds and expires after 30 seconds without renewal.
- The Coordinator retains client registrations, even after a GUI disconnects. A registered client may be offline or lack a ready dataset.
- Uploaded CSVs are kept **in process memory**, not persisted in a Client PVC. Re-upload and reconnect after a Client GUI process/Pod restart.

## Trust Scores and final evaluation

TrustFed Trust Scores are committed by the Coordinator after aggregation. Each client card displays the **real numerical score plus a proportional bar** when a score is available. These numbers are not live connection health, scam probabilities or model accuracy. A score may remain from the last published model while a new round is in progress.

After five successful rounds, the Coordinator GUI allows a final evaluation CSV to be selected. Evaluation uses the model retrieved through `GET /model/current`, computes accuracy, precision, recall and F1-score **in the Coordinator GUI process**, and does not change the model in Kubernetes. The Coordinator GUI provides model results; it does not host the federated training clients.

## Useful API endpoints

With the Coordinator API on port 8000:

- `GET /health` — service and aggregation mode.
- `GET /clients` — persisted client registrations.
- `GET /clients/status` — online/dataset-ready status and sample counts.
- `GET /rounds/current` and `GET /rounds/progress` — current round and five-round progress.
- `GET /model/current` and `GET /model/trust-scores` — published model and committed scores.

The GUI processes also provide their own `GET /api/status` endpoint, used for GUI status and per-client training-event history.

## Limitations

- The prototype GUIs and Coordinator API have no authentication; keep connections local or in a trusted network.
- Kubernetes Pod `Running` / `Ready` does not mean a client has selected a dataset or clicked **Connect**.
- SQLite state is persistent but transient online presence is not. A rebooted Coordinator needs new client heartbeats before displaying clients online.
- The Coordinator GUI is not included in `Dockerfile.coordinator` and is not deployed inside its Kubernetes Pod.
- The optional `visualization/` component **is required for the current Kubernetes Client GUI deployment**: `Dockerfile.client` copies it and the StatefulSet launches `visualization.app client`. Do not remove it unless you also restore a CLI-only client deployment.
