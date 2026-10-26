# TrustFed: local GUI + Kubernetes integration

This change is deliberately small. The local GUI demo still works. In Kubernetes mode, **the cluster** runs the coordinator and five client Pods; **only the coordinator GUI** runs locally.

## Modified files

- `coordinator/round_manager.py`: read-only, lock-protected snapshot of committed trust scores.
- `coordinator/main.py`: `GET /model/trust-scores`, returning `model_version` and `trust_scores`.
- `visualization/app.py`: use the HTTP endpoint first; safely fall back to matching local SQLite when using an older local coordinator.
- `kubernetes/coordinator-deployment.yaml`: enables TrustFed aggregation, uses Member 5's validation CSV, and mounts the persistent volume at `/app/state` so `/app/data` remains accessible.
- `visualization/README.md`: documents both modes.
- `tests/test_role3_trust_score_api.py`: persistence and API data-contract regression test.

No training algorithm or client Pod source code is changed.

## 1. Prerequisites

On your Mac, enable Docker Desktop and its Kubernetes cluster. From the project directory:

```bash
docker info
kubectl config current-context
kubectl get nodes
python -m pytest -q
```

Check that `kubectl` is pointed at your intended test cluster before deploying.

## 2. Build the images using the same tags as the YAML

```bash
docker build -f Dockerfile.coordinator -t localhost/trustfed-coordinator:v2 .
docker build -f Dockerfile.client -t localhost/trustfed-client:v1 .
```

The Docker Desktop Kubernetes setup must have access to these locally built images. On a separate cluster, push images to a registry and update both image references in the YAML.

## 3. Deploy

```bash
kubectl apply -f kubernetes/
kubectl rollout status deployment/coordinator --timeout=180s
kubectl rollout status statefulset/trustfed-clients --timeout=180s
kubectl get pods
kubectl get svc trustfed-coordinator
```

Expected: one coordinator Pod and five client Pods. Pod readiness and restart counts matter; a client being registered in the GUI is not proof of Pod health.

Check that the validation file is available inside the coordinator:

```bash
kubectl exec deployment/coordinator -- ls -l /app/data/coordinator_val_set.csv
```

View client logs when troubleshooting:

```bash
kubectl logs trustfed-clients-0 --tail=30
```

## 4. Connect the local GUI

**Stop the local `server` alias first** (port 8000 must be free). Also stop local `client1`, `client2`, `client3` training GUIs to avoid duplicate clients.

Terminal A:

```bash
kubectl port-forward svc/trustfed-coordinator 8000:8000
```

Terminal B, from project root:

```bash
python -m visualization.app coordinator --port 8500 --coordinator-url http://127.0.0.1:8000
```

Open http://127.0.0.1:8500. Check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/clients
curl http://127.0.0.1:8000/model/trust-scores
```

`/health` should report `aggregation_mode` as `trustfed`. Start a round with a generous deadline (e.g. 120 seconds), then watch real Pods submit updates. The coordinator will finalize the round automatically after the deadline. A new model is published only if at least three updates are accepted.

## 5. Important distinctions

- The GUI displays actual coordinator state and committed trust scores. It does not display or invent Pod CPU usage, cluster scaling, real-time liveness or model accuracy.
- Run `kubectl get pods -w` in a separate terminal to demonstrate Member 4's infrastructure.
- The local `reset` alias removes **only your local SQLite database**; it does not reset a Kubernetes PVC.
- Your local `server`, `coord`, `client1`, `client2`, `client3` workflow is unchanged. For the Kubernetes demo, use **only `coord`**, after starting port-forward.
- The endpoint has no authentication, consistent with the other prototype coordinator API routes. Keep the port-forward bound to localhost; do not expose it to the public internet.
- The YAML references one coordinator replica and a ReadWriteOnce volume. Do not scale the coordinator horizontally with this SQLite design.

## Verified and unverified

Verified: 45 pre-existing Python tests, an additional trust-score persistence test, and an end-to-end local HTTP check in which a TrustFed aggregation published v1 and the coordinator GUI successfully retrieved three scores without accessing the coordinator SQLite file.

Not verified: building Docker images and running Kubernetes Pods in this execution environment (Docker and kubectl were unavailable). Run the deployment checks above on your Mac.
