# TrustFed

Trust-Aware Federated Learning for Decentralised Scam Message Detection

## Project Overview

TrustFed investigates whether trust-aware aggregation can improve federated scam-message detection under corrupted client updates and client failures. 

The system consists of a central FastAPI Coordinator and multiple simulated Federated Learning clients, all running as microservices inside a Kubernetes cluster.

## Proposed Features

- Federated learning across multiple simulated clients
- FedAvg baseline
- Trust-aware aggregation using validation F1-scores
- Historical client reliability tracking
- Corrupted-update and client-dropout experiments
- FastAPI coordinator
- Docker and Kubernetes deployment

## Current Implementation

- [x] Python development environment
- [x] Centralised TF-IDF + SGDClassifier baseline
- [x] Real dataset split into 5 clients (`client_1_train.csv` to `client_5_train.csv`)
- [x] Federated client training
- [x] FedAvg aggregation
- [x] Trust-aware aggregation
- [x] Distributed coordinator
- [x] Docker deployment
- [x] Kubernetes deployment
- [x] Fault-tolerant persistent storage
- [ ] Robustness evaluation (Member 6)

## Architecture & Kubernetes Deployment

The system is deployed using Kubernetes to simulate a distributed environment:

- **Coordinator (`Deployment`)**: Runs the FastAPI server. It is exposed internally via a `ClusterIP` service (`http://trustfed-coordinator:8000`).
- **Clients (`StatefulSet`)**: We use a StatefulSet with `replicas: 5` to guarantee stable network identities (`trustfed-clients-0` through `-4`). The script maps the pod index to the correct CSV file (e.g., Pod 0 reads `client_1_train.csv`).
- **Storage (`PersistentVolumeClaim`)**: A PVC (`trustfed-pvc`) is mounted to `/app/data` to store the SQLite database, ensuring the global model and client trust scores survive pod crashes.
- **Resource Management**: CPU and Memory limits are explicitly set for all pods to prevent resource starvation.

---

## 🚀 Step-by-Step Setup Guide

**Prerequisites:** Docker Desktop (with WSL2 backend on Windows) and Kubernetes enabled.

### Step 1: Build the Docker Images
*Note: We use `--no-cache` to prevent Docker from using old, cached CSV data.*

```bash
# Build the Coordinator (using v2)
docker build --no-cache -f Dockerfile.coordinator -t localhost/trustfed-coordinator:v2 .

# Build the Clients (using v1)
docker build --no-cache -f Dockerfile.client -t localhost/trustfed-client:v1 .

# Deploy to Kubernetes
kubectl apply -f kubernetes/

# Access Coordinator API
kubectl port-forward svc/trustfed-coordinator 8000:8000
navigate to http://localhost:8000/
```

The coordinator serves the TrustFed dashboard at `http://localhost:8000/`.
The original FastAPI documentation remains available at
`http://localhost:8000/docs`.

For local development, start the coordinator as usual:

```powershell
python -m uvicorn coordinator.main:app --reload --port 8000
```

The downloaded GUI is also available as a standalone application when you
need a separate client window:

```powershell
python -m visualization.app client --port 8501 --coordinator-url http://127.0.0.1:8000