# TrustFed

**Trust-Aware Federated Learning for Decentralised Scam Message Detection**

CSC3104 Cloud and Distributed Computing — Group 13

TrustFed is a federated-learning prototype in which separate clients train a shared scam-message classifier without sending their raw training messages to the Coordinator. The Coordinator manages training rounds, validates submitted models, applies FedAvg or trust-aware aggregation, and publishes the updated global model.

## Current architecture

| Component | Implementation | Role |
| --- | --- | --- |
| Coordinator backend | FastAPI; one Kubernetes `Deployment` Pod | Registration, rounds, update validation, aggregation, global model, Trust Scores |
| Clients | Three Kubernetes `StatefulSet` Pods | Each hosts the existing Client GUI, accepts a CSV and trains its own model |
| Coordinator GUI | Browser UI served by a separate local Python process | Starts rounds, monitors readiness/results and evaluates the final model |
| Persistence | SQLite on PVC `trustfed-pvc` at `/app/state` | Keeps registrations, round/model state and committed Trust Scores across Coordinator Pod restarts |

In the current Kubernetes configuration, **three** clients run in Pods `trustfed-clients-0`, `-1` and `-2`. The Client GUIs run **inside** these Pods; the browser connects through `kubectl port-forward`. The Coordinator GUI still runs on the host computer, connected to the Coordinator's service through a port-forward. See [Kubernetes GUI integration](docs/GUI_KUBERNETES_INTEGRATION.md) for the full explanation.

The repository also retains `data/client_4_train.csv` and `data/client_5_train.csv` for experiments. The default three-Pod GUI deployment does **not** automatically train on any bundled CSV: select a file in each Client GUI and click **Connect**. Training then runs in that Pod when a round begins.

## Implemented features

- Shared text-classification model with client-side training (`SGDClassifier` and hashing features).
- Federated model exchange (updated parameters and sample counts, **not** raw training CSVs).
- FedAvg and TrustFed aggregation, with validation and historical Trust Scores.
- Manual round starts, deadlines, accepted/rejected submissions, and skipped rounds when there are fewer than three accepted updates.
- Three-client readiness reporting: client heartbeat every 10 seconds, with online presence expiring after 30 seconds; dataset-ready status and sample count shown in the Coordinator GUI.
- Progress toward **five successful rounds**. Skipped attempts do not count, and starting a sixth successful round is blocked.
- Final global-model evaluation with a user-selected CSV: accuracy, precision, recall and F1-score. Evaluation does not retrain or overwrite the global model.
- SQLite-backed Coordinator recovery, automated tests, Docker and Kubernetes deployment.

**Evaluation note:** In the current implementation, the selected evaluation CSV is processed by the *local Coordinator GUI backend*, which retrieves the global model through the Coordinator API. Evaluation processing is **not** inside the Kubernetes Coordinator Pod.

## Requirements

- Python 3.12+ recommended, with dependencies from `requirements.txt`.
- For Kubernetes: Docker Desktop with Kubernetes enabled, `docker` and `kubectl`.
- Docker Desktop's local cluster is the setup used for the project demo; another cluster needs access to the built images (for example, via an image registry).

On macOS, from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

For **every new terminal** running a Python command, go to the repository root and run `source .venv/bin/activate` first. The environment does not carry over to a new terminal. The full local-GUI walkthrough is in [visualization/README.md](visualization/README.md).

## Run with Kubernetes (three Client GUIs)

### 1. Check Docker Desktop and Kubernetes

```bash
docker info
kubectl config current-context
kubectl get nodes
```

Confirm you're using the intended cluster and the node is `Ready`.

### 2. Build the Docker images

The checked-in Kubernetes YAML references **Coordinator `v3`** and **Client `v2`**:

```bash
docker build -f Dockerfile.coordinator -t localhost/trustfed-coordinator:v3 .
docker build -f Dockerfile.client -t localhost/trustfed-client:v2 .
```

On Docker Desktop Kubernetes, the cluster can use these local images. On remote clusters, publish them to an accessible registry and change the YAML image references. If you rebuild an image **under the same tag**, Kubernetes may keep using its cached image because the YAML uses `imagePullPolicy: IfNotPresent`; use a fresh tag (and update YAML) or deliberately roll out the rebuilt image.

### 3. Deploy

```bash
kubectl apply -f kubernetes/storage.yaml
kubectl apply -f kubernetes/coordinator-service.yaml
kubectl apply -f kubernetes/coordinator-deployment.yaml
kubectl apply -f kubernetes/clients-statefulset.yaml

kubectl rollout status deployment/coordinator --timeout=180s
kubectl rollout status statefulset/trustfed-clients --timeout=180s
kubectl get pods
```

Expected: **one Coordinator Pod** and **three Client Pods** (`trustfed-clients-0`, `-1`, `-2`). The `trustfed-clients-headless` service is defined in the StatefulSet YAML.

### 4. Start port-forwards

Run each command in its **own terminal**; leave it running:

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

Stop any old **local** Coordinator backend or local Client GUI on these ports first, to avoid conflicts. The client containers all listen internally on port `8501`; their host ports differ.

In another terminal at the project root, start the **local Coordinator GUI**:

```bash
source .venv/bin/activate
python -m visualization.app coordinator --port 8500 --coordinator-url http://127.0.0.1:8000
```

### 5. Upload data, connect and train

| Browser | Client ID | Example CSV |
| --- | --- | --- |
| http://127.0.0.1:8500 | Coordinator GUI | Final test CSV after training |
| http://127.0.0.1:8501 | `client-1` | `data/client_1_train.csv` |
| http://127.0.0.1:8502 | `client-2` | `data/client_2_train.csv` |
| http://127.0.0.1:8503 | `client-3` | `data/client_3_train.csv` |

For each Client GUI, select a CSV containing `text,label` (or `message,label`), with nonempty message text and labels `0` or `1`; then click **Connect**. An `OFFLINE` client before connecting is expected. Each client sends heartbeats once connected; the Coordinator should display **3/3 ready** when all three are ready.

From the Coordinator GUI, start rounds manually and wait for finalization. A successful round needs at least **three accepted client updates**. Continue until the GUI shows **5/5 successful rounds** and global model `v5`. Select `data/final_test_set.csv` in **Final Model Evaluation** to display accuracy, precision, recall and F1-score.

### 6. Check the application and cluster

```bash
kubectl get pods
kubectl get statefulset trustfed-clients
kubectl exec deployment/coordinator -- printenv TRUSTFED_DB_PATH
```

The Coordinator API is available at http://127.0.0.1:8000/docs while its port-forward is active. Useful read-only endpoints include `/health`, `/clients`, `/clients/status`, `/rounds/progress`, `/model/current` and `/model/trust-scores`.

For Pod-level verification and troubleshooting, see [docs/GUI_KUBERNETES_INTEGRATION.md](docs/GUI_KUBERNETES_INTEGRATION.md).

## Persistence and test-state caveat

The Coordinator YAML uses `TRUSTFED_DB_PATH=/app/state/coordinator.sqlite3`, stored on PVC `trustfed-pvc`. Changing from five client Pods to three **does not delete** previously registered Clients 4 and 5 from this database. Registration persists; liveness is based separately on current heartbeats.

To run a clean demonstration **without deleting the previous database**, you can switch the deployment to a different database filename:

```bash
kubectl set env deployment/coordinator TRUSTFED_DB_PATH=/app/state/coordinator-3clients-test.sqlite3
kubectl rollout status deployment/coordinator --timeout=180s
```

This changes the **live Deployment**, not the checked-in YAML. Reapplying `kubernetes/coordinator-deployment.yaml` can restore its original database path. Do not delete `trustfed-pvc` just to clear registration history.

## Test coverage and limits

```bash
source .venv/bin/activate
python -m pytest -q
```

The project was last verified with **67 passing Python tests** on the three-client implementation, and a separate Docker Desktop Kubernetes run completed five accepted rounds across three actual Client Pods. Re-run tests after changing source files.

The demonstration APIs and GUIs do **not** implement authentication. Use localhost port-forwarding or a trusted environment; do not expose these endpoints publicly. The Coordinator is designed for **one process/replica** using its SQLite file, not horizontally scaled concurrent writers. Uploaded training CSVs are held in a Client GUI process and must be selected again after its Pod restarts; they are not stored permanently on a Client PVC.
