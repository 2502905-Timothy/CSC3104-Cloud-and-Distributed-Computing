# TrustFed

Trust-Aware Federated Learning for Decentralised Scam Message Detection

## Project Overview

TrustFed investigates whether trust-aware aggregation can improve federated scam-message detection under corrupted client updates and client failures.

The system enables multiple distributed clients to train models locally while a FastAPI coordinator manages training rounds, collects model updates, and performs trust-aware aggregation.

## Proposed Features

- Federated learning across multiple simulated clients
- FedAvg baseline
- Trust-aware aggregation using validation F1-scores
- Historical client reliability tracking
- Corrupted-update and client-dropout experiments
- FastAPI coordinator
- Docker and Kubernetes deployment
- Interactive Next.js project presentation

## Current Implementation

- [x] Python development environment
- [x] Centralised TF-IDF + SGDClassifier baseline
- [x] Synthetic dataset for initial testing
- [x] Federated client training
- [x] FedAvg aggregation
- [x] Trust-aware aggregation
- [x] Historical client reliability tracking
- [x] Distributed FastAPI coordinator
- [x] Docker deployment with three federated clients
- [x] Kubernetes deployment configurations
- [x] Next.js interactive presentation frontend
- [x] Automated testing (45 tests passed)
- [x] Successful federated learning round with 3/3 client updates accepted
- [ ] End-to-end Kubernetes deployment verification
- [ ] Full robustness evaluation and FedAvg comparison

## Requirements

Python 3.14 with the dependencies listed in `requirements.txt`.

Docker Desktop and Node.js are required for the containerised deployment and presentation frontend, respectively.

## Run the Current Baseline

Install dependencies:

```cmd
python -m pip install -r requirements.txt
```

Run the experiment from the repository root:

```cmd
python -m experiments.evaluate
```

Run automated tests:

```cmd
python -m pytest tests -q
```

## Docker Deployment

Build the coordinator and client Docker images:

```cmd
docker build -f Dockerfile.coordinator -t trustfed-coordinator:demo .
docker build -f Dockerfile.client -t trustfed-client:demo .
```

Create a Docker network:

```cmd
docker network create trustfed-demo
```

Start the TrustFed coordinator:

```cmd
docker run -d --name trustfed-coordinator --network trustfed-demo -p 8000:8000 -e TRUSTFED_AGGREGATOR=trustfed -e TRUSTFED_VALIDATION_PATH=/app/data/validation_messages.csv -e TRUSTFED_DB_PATH=/app/trustfed_demo.sqlite3 trustfed-coordinator:demo
```

Verify the coordinator:

```cmd
curl http://localhost:8000/health
```

After starting and registering the federated clients, initiate a training round:

```cmd
curl -X POST http://localhost:8000/rounds/start -H "Content-Type: application/json" -d "{\"deadline_seconds\":60}"
```

Check the training round:

```cmd
curl http://localhost:8000/rounds/current
```

## Verified Results

A local Docker demonstration successfully completed one federated learning round with:

- 1 FastAPI coordinator and 3 federated learning clients
- 3/3 client updates received and accepted
- Trust-aware aggregation enabled
- Automatic round completion and finalisation
- Global model version updated from 0 to 1

## Important Notes

The initial dataset contains 20 synthetic messages and is used only for development testing.

Initial accuracy and F1-score are approximately 0.3333 on a six-message test split. These results are not representative of real-world detection performance.

Trust-aware aggregation and distributed training have been implemented and verified locally using Docker. Kubernetes deployment verification and comprehensive robustness experiments are still in progress.
