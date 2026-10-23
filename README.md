
# TrustFed

Trust-Aware Federated Learning for Decentralised Scam Message Detection

## Project Overview

TrustFed investigates whether trust-aware aggregation can improve
federated scam-message detection under corrupted client updates
and client failures.

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
- [x] Synthetic dataset for initial testing
- [ ] Federated client training
- [ ] FedAvg aggregation
- [ ] Trust-aware aggregation
- [ ] Distributed coordinator
- [ ] Docker deployment
- [ ] Kubernetes deployment
- [ ] Robustness evaluation

## Requirements

Python 3.14 with the dependencies listed in requirements.txt.

## Run the Current Baseline

Install dependencies:

```cmd
python -m pip install -r requirements.txt
```

Run the experiment from the repository root:

```cmd
python -m experiments.evaluate
```

## Important Notes

The initial dataset contains 20 synthetic messages and is used
only for development testing.

Initial accuracy and F1-score are approximately 0.3333 on a
six-message test split. These results are not representative
of real-world detection performance.

The federated and trust-aware components are still under development.
