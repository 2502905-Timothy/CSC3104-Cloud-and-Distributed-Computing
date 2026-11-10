# TrustFed GUI + Kubernetes integration

This guide describes the **current three-client Kubernetes deployment**. It replaces the older five-Pod, CLI-only workflow. The project retains a separate **local-only mode** for development, documented in [visualization/README.md](../visualization/README.md).

## Where each component runs

| Component | Kubernetes mode | What it does |
| --- | --- | --- |
| FastAPI Coordinator | `coordinator` Deployment, 1 Pod, port 8000 | Registers clients, manages rounds, validates/aggregates submissions, stores global model and Trust Scores |
| Client 1 GUI and trainer | `trustfed-clients-0`, internal port 8501 | Accepts Client 1's CSV, trains within Pod 0 |
| Client 2 GUI and trainer | `trustfed-clients-1`, internal port 8501 | Accepts Client 2's CSV, trains within Pod 1 |
| Client 3 GUI and trainer | `trustfed-clients-2`, internal port 8501 | Accepts Client 3's CSV, trains within Pod 2 |
| Coordinator GUI | Local host process, usually port 8500 | Calls the Coordinator API and locally evaluates the downloaded final model |
| SQLite | `trustfed-pvc` mounted at `/app/state` in Coordinator Pod | Persists Coordinator state across Pod replacement |

`Dockerfile.client` copies the existing `visualization/` application into each client image. The StatefulSet starts `python -m visualization.app client --host 0.0.0.0 --port 8501 --coordinator-url http://trustfed-coordinator:8000`, **not** the old CLI command that automatically read a preset CSV. The client data remains with the Client GUI process inside its Pod; only model updates, sample counts and readiness heartbeats go to the Coordinator.

The Coordinator GUI is a **different** web server. It runs on the host and accesses Kubernetes through a local service port-forward. Selecting a final evaluation CSV in that GUI evaluates the final global model locally, not inside the Coordinator Pod.

## Prerequisites and environment

From the repository root:

```bash
python3 -m venv .venv            # first-time setup only
source .venv/bin/activate
python -m pip install -r requirements.txt   # first-time setup or dependency changes
python -m pytest -q

docker info
kubectl config current-context
kubectl get nodes
```

Start Docker Desktop and enable Kubernetes before deployment. Make sure `kubectl` targets the intended cluster. Repeat `source .venv/bin/activate` **in each new terminal that executes Python**. `kubectl` and `docker` do not require the Python virtual environment.

## Build and deploy

The image tags below match the current YAML:

```bash
docker build -f Dockerfile.coordinator -t localhost/trustfed-coordinator:v3 .
docker build -f Dockerfile.client -t localhost/trustfed-client:v2 .
docker images | grep trustfed

kubectl apply -f kubernetes/storage.yaml
kubectl apply -f kubernetes/coordinator-service.yaml
kubectl apply -f kubernetes/coordinator-deployment.yaml
kubectl apply -f kubernetes/clients-statefulset.yaml

kubectl rollout status deployment/coordinator --timeout=180s
kubectl rollout status statefulset/trustfed-clients --timeout=180s
kubectl get pods
```

Expect **one Coordinator and three Client Pods**, each `1/1 Running`. On Docker Desktop, the locally built images are accessible to the local cluster. Other clusters need a registry accessible to their nodes and matching image references in YAML. With `imagePullPolicy: IfNotPresent`, rebuilding under an existing tag does not guarantee a running Pod uses a new image; use a new image tag or deliberately restart/replace Pods with the intended image.

The Client StatefulSet's `replicas: 3` defines all three Pods in **one YAML file**. A separate YAML file per client isn't required.

## Access the GUIs

Keep each port-forward running in its own terminal:

| Target | Command | Open in browser |
| --- | --- | --- |
| Coordinator API | `kubectl port-forward svc/trustfed-coordinator 8000:8000` | http://127.0.0.1:8000/docs |
| Client Pod 0 | `kubectl port-forward pod/trustfed-clients-0 8501:8501` | http://127.0.0.1:8501 |
| Client Pod 1 | `kubectl port-forward pod/trustfed-clients-1 8502:8501` | http://127.0.0.1:8502 |
| Client Pod 2 | `kubectl port-forward pod/trustfed-clients-2 8503:8501` | http://127.0.0.1:8503 |

Stop any local backend on `8000` and locally running Client GUIs on `8501`–`8503` before port-forwarding. The numbers before the colon are **Mac/local ports**; the number after the colon is the **Pod port**.

Open a fifth terminal from the repository root:

```bash
source .venv/bin/activate
python -m visualization.app coordinator --port 8500 --coordinator-url http://127.0.0.1:8000
```

Browse to http://127.0.0.1:8500 for the Coordinator GUI. It reads real server state from the Coordinator Pod over HTTP. Pod resource health and container readiness are checked through `kubectl`, not inferred from client registration alone.

## End-to-end three-client training test

1. On the Client GUIs at ports `8501`, `8502` and `8503`, enter distinct IDs `client-1`, `client-2` and `client-3`.
2. Select `data/client_1_train.csv`, `data/client_2_train.csv` and `data/client_3_train.csv` respectively, or another valid CSV with a `text,label` / `message,label` header. Accepted labels are `0` and `1`.
3. Click **Connect** on each GUI. Seeing `OFFLINE` before doing so is normal. The Client GUI validates its CSV and starts reporting dataset readiness and sample count to the Coordinator.
4. Confirm **3/3 ready** in the Coordinator GUI. Clients heartbeat roughly every **10 seconds**; an absent heartbeat makes them offline after **30 seconds**. Old registrations can still remain listed.
5. Start Round 1 from the Coordinator GUI; after the deadline, verify **three accepted updates**, model `v1` and successful progress `1/5`. The Coordinator needs **at least three accepted** updates to publish an updated model.
6. Repeat through **five successful rounds** and model `v5`. Skipped attempts do not count toward five. The Start Round action is blocked after five successful publications.
7. In the **Final Model Evaluation** section, select `data/final_test_set.csv` (or another valid held-out test CSV) and evaluate. The interface displays accuracy, precision, recall, F1-score and number of test samples. This step does **not** modify the global model.

Client messages are not sent to the Coordinator; the Coordinator receives the resulting model parameters and reported sample counts. Uploaded CSVs live in the Pod-hosted Client GUI's memory. After a Pod restart, upload and connect again.

### Verify training actually ran inside Pods

A `1/1 Running` status only proves the container is running, **not** that a client registered or trained. Inspect each Pod's own `/api/status` endpoint:

```bash
for i in 0 1 2; do
  echo "=== Client Pod $i ==="
  kubectl exec "trustfed-clients-$i" -- python -c '
import json, urllib.request
s = json.load(urllib.request.urlopen("http://127.0.0.1:8501/api/status"))
print("Client:", s["client_id"])
print("Status:", s["status"])
print("Samples:", s["sample_count"])
for event in reversed(s["events"]):
    if "Round " in event["message"]:
        print(event["message"])
'
done
```

Expected evidence after five rounds: for each Pod, successive model downloads, five submitted updates and final accepted status. The log text *"training locally"* refers to local training **within that Pod's client process**, not training on the Mac. `kubectl logs` may be empty because these events are retained in the GUI status response rather than printed to stdout.

## Persistence: old client registrations after scaling down

The Coordinator uses `TRUSTFED_DB_PATH=/app/state/coordinator.sqlite3` in `kubernetes/coordinator-deployment.yaml`. That location is backed by the `trustfed-pvc` volume. Scaling from five Client Pods to three **does not unregister Clients 4 and 5**, and replacing the Coordinator Pod does not erase the database.

For a fresh three-client **test** without deleting old history, choose a different SQLite filename on the same volume:

```bash
kubectl set env deployment/coordinator TRUSTFED_DB_PATH=/app/state/coordinator-3clients-test.sqlite3
kubectl rollout status deployment/coordinator --timeout=180s
kubectl exec deployment/coordinator -- printenv TRUSTFED_DB_PATH
```

To confirm a new, empty registration list (before connecting any clients):

```bash
kubectl exec deployment/coordinator -- python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/clients").read().decode())'
```

If that chosen filename already contains a prior test, use a **new unique filename** instead. The `kubectl set env` change is runtime-only: the checked-in YAML still specifies `/app/state/coordinator.sqlite3`, so reapplying it may restore that path. A Coordinator restart or re-deployment can interrupt port-forwarding; restart it if necessary. **Do not delete the PVC or your existing SQLite database to reset a demo.**

Presence is **not** persisted. Registered clients may show offline just after Coordinator restart until they send fresh heartbeats; this is expected.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Docker/Kubernetes connection refused | Open Docker Desktop; confirm `docker info` and `kubectl get nodes` work |
| Still seeing five Client Pods | Check `kubectl get statefulset trustfed-clients`; apply the updated `clients-statefulset.yaml` and verify rollout |
| Only three Pods but GUI lists five clients | Old persistent SQLite registrations; see the fresh test DB section above |
| Client GUI not reachable | Check `kubectl get pods`, its `kubectl port-forward`, browser port, and `kubectl describe pod` |
| Client GUI says `OFFLINE` | Upload a valid CSV and click **Connect**; Pod readiness alone does not register the client |
| Coordinator GUI cannot connect | Confirm Coordinator service port-forward on `8000`; restart forwarding after Pod replacement |
| Deployment runs old behavior | Check the image tags in YAML, node image access and `IfNotPresent` caching |
| A round is skipped | Fewer than three accepted updates; review participants/submissions and client `/api/status` events |

Useful commands:

```bash
kubectl get pods -w
kubectl describe pod trustfed-clients-0
kubectl logs deployment/coordinator --tail=80
kubectl logs trustfed-clients-0 --tail=80
kubectl exec trustfed-clients-0 -- python -c 'print(open("/proc/1/cmdline", "rb").read().replace(b"\0", b" ").decode())'
```

## Scope and security

- The Coordinator supports one active SQLite-backed replica, not multiple concurrent Coordinator writers.
- GUI and API endpoints have no authentication. Port-forward to localhost and avoid public exposure.
- Coordinator and Client GUIs can also run in **local-only mode**, but that is different from Pod-hosted training. See [visualization/README.md](../visualization/README.md).
- Docker/Kubernetes deployment verification is separate from the Python test suite. The latest recorded automated run contained 67 passing tests; the three-Pod Kubernetes demonstration also completed five accepted rounds.
