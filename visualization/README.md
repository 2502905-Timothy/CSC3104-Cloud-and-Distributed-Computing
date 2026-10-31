# TrustFed demonstration GUI — compact trust display

This is an **optional, local demonstration interface**, kept separate from the group's production backend. Its two screens are deliberately uncluttered:

- **Coordinator**: global model version, current round, deadline, update counts, registered-client status, accepted/rejected decisions, and actual committed TrustFed scores obtained through the coordinator API (or local SQLite fallback for older backends).
- **Client**: choose your own CSV, register, train locally when a round starts, submit updates, and show training status plus scam/legitimate dataset counts.

The GUI calls the real coordinator API and `client.train.local_train`; it **does not simulate trust scores, predict acceptance, or run Kubernetes**. The coordinator GUI reads committed trust scores over a **read-only HTTP API** when available; the matching SQLite file is a fallback for older local backends. The training CSV remains in its own client's GUI process, not at the coordinator.

## Installation

From the project root, replace your existing **untracked** `visualization/` directory with the `visualization/` folder in this ZIP, or copy just `visualization/app.py`, `visualization/ui.html`, and `visualization/README.md` over the corresponding existing files. No files outside `visualization/` are changed. Keep your old local version if you have personal changes to it.

## Run locally — TrustFed aggregation

Activate the repo's virtual environment, then open **five terminals** in the repository root. A fresh database helps make the model versions easy to show.

**Terminal 1 — Coordinator**

```bash
mkdir -p "$HOME/.trustfed"
export TRUSTFED_AGGREGATOR=trustfed
export TRUSTFED_DB_PATH="$HOME/.trustfed/trustfed-presentation.sqlite3"
export TRUSTFED_VALIDATION_PATH=data/coordinator_val_set.csv
python -m uvicorn coordinator.main:app --host 127.0.0.1 --port 8000
```

If that exact `.sqlite3` file already exists, its model and registrations will persist. Choose a fresh filename for an initial v0 demo; do not delete a database you need to keep.

**Terminal 2 — Coordinator GUI**

With an updated coordinator the GUI fetches trust scores over HTTP. The database path below is only needed as a fallback for an older coordinator:

```bash
export TRUSTFED_DB_PATH="$HOME/.trustfed/trustfed-presentation.sqlite3"
python -m visualization.app coordinator --port 8500
```

Alternatively, pass `--state-db "$HOME/.trustfed/trustfed-presentation.sqlite3"` on the command line; this works even if the database environment variable was only set in terminal 1.

**Terminals 3–5 — Individual client GUIs**

```bash
python -m visualization.app client --port 8501
python -m visualization.app client --port 8502
python -m visualization.app client --port 8503
```

Open:

| Screen | Browser address | Dataset to select |
| --- | --- | --- |
| Coordinator | http://127.0.0.1:8500 | No CSV |
| Client 1 | http://127.0.0.1:8501 | `data/client_1_train.csv` |
| Client 2 | http://127.0.0.1:8502 | `data/client_2_train.csv` |
| Client 3 | http://127.0.0.1:8503 | `data/client_3_train.csv` |

For each client, enter a **unique** ID (for example, `client-1`) and select the indicated CSV, then click **Connect Client**. From the coordinator window, start a training round. Wait for the deadline; on a successful round, the coordinator should publish the next global model version. Its saved trust scores will show directly underneath the corresponding clients' names.

The coordinator requires at least **three accepted** updates to publish a new model. Received submissions are not automatically accepted. With fewer than three accepted updates, the model version doesn't advance. Registered clients are not necessarily online.

## What do the trust numbers mean?

They are real **last committed trust scores**, retrieved from the coordinator API (or a matching local SQLite snapshot on older backends). They are **not** live connection health, attack probabilities, guaranteed accuracy, or thresholds automatically used to accept every client. Trust scores remain from earlier successful model publication while new rounds are running. Rejected clients may have no saved score. A short note on the GUI explains this.

The GUI deliberately doesn't expose raw client messages, validation data, or a fake accuracy graph. Client-side label counts only describe the selected training CSV; they are not accuracy results.

If scores say *unavailable*, verify the coordinator exposes `GET /model/trust-scores`. Older backends require the GUI to access the **same SQLite database** through `TRUSTFED_DB_PATH` or `--state-db`. No scoring values are invented or cached as substitutes. In `fedavg`/`mock` modes the trust display is hidden.

## Notes and limitations

- Local demonstrations don't prove container/pod health. Show Kubernetes separately using actual deployment tools if needed.
- GUI instances have no authentication; use only on localhost or a trusted network. Client CSV contents travel to the local client GUI process in order to train.
- A rejected update's reason isn't currently included in the coordinator API. The GUI reports only the genuine accepted/rejected decision, not an invented explanation.
- Registration persists in the coordinator. Stopping a client GUI stops its polling but does **not** unregister it.
- To remove the optional demo, stop GUI processes and delete `visualization/`; the rest of the project's Python backend and SQLite state are unaffected.

## Kubernetes coordinator with the SAME local GUI

The coordinator and five clients can instead run as Kubernetes Pods. The GUI stays on your Mac; it talks to the coordinator over a Kubernetes port-forward. **Do not run `server` or the three local GUI training clients at the same time as the cluster demo.** The five Kubernetes Pods are already real clients.

From the repository root (after deploying the cluster), keep this running in a terminal:

```bash
kubectl port-forward svc/trustfed-coordinator 8000:8000
```

In another terminal start just the coordinator GUI:

```bash
python -m visualization.app coordinator --port 8500 --coordinator-url http://127.0.0.1:8000
```

Visit http://127.0.0.1:8500. The GUI reads the live client list, round status, model version, and committed trust scores through HTTP; it does not need the cluster's database file or access to Kubernetes itself. For actual Pod health/status, use `kubectl get pods` or Kubernetes logs; registered clients do not prove a Pod is online.
