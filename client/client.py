# Federated client: registers, waits for a collecting round, trains locally submits.

# The Client lifecycle (repeats every round)
# 1. Register with the coordinator (once)
# 2. Poll the coordinator:"Is a round open for me?"
# 3. Download the current global model
# 4. Train it on local private data(client/train.py)
# 5. Uplaod the improved model + how many messages it used.

# Usage:
#     python -m client.client --client-id client_a --data data/client_a.csv \
#         --coordinator http://localhost:8000 --max-rounds 10
#     CSV needs colums: text,label (label: 1 = scam, 0 = legitimate)

import argparse
import csv
import time
import requests
from client.train import local_train


# Read the client's private data. Returns (list of texts, list of 0/1 labels)
# Function to be changed if member 5 does a different file format

def load_csv(path: str):
    with open(path, newline= "", encoding = "utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    column = "message" if rows and "message" in rows[0] else "text"
    return [r[column] for r in rows], [int(r["label"]) for r in rows]

def run(client_id :str, data_path: str, url: str, epochs: int, max_rounds:int, poll: float):
    #Main loop: keep checking the coordinator and take part in rounds until done.
    texts, labels = load_csv(data_path)
    http = requests.Session()
    
    #Step 1: Register
    r = http.post(f"{url}/clients/register", json = {"client_id": client_id}, timeout=10)
    if r.status_code not in (201,409):     #201 = newly registered, 409 = already registered
        r.raise_for_status()               #(409 is fine: happens when a client restarts)
        
    done = 0            #how many rounds we successfully submitted to
    last_round = 0      #highest round we already tried, so we never submit twice to one round
    
    while done < max_rounds:
        time.sleep(poll)
        try:
            #Step 2: Ask for what the current round looks like
            rnd = http.get(f"{url}/rounds/current", timeout = 10)
            if rnd.status_code == 404:
                continue
            rnd.raise_for_status()
            info = rnd.json()
            
            #Skips this check cycle and look again unless ALL of this holds:
            if(
                info["status"] != "collecting"              # round must be open for updates
                or info["round_id"] <= last_round           # not a round we already handled
                or client_id not in info["participants"]    #we must be part of this round
                or client_id in info["submitted_clients"]   #We must not have submitted already
            ):
                continue
            
            #Step 3: download the current global model
            model = http.get(f"{url}/model/current", timeout=10).json()
            if model["model_version"] != info["model_version"]:
                continue
            
            #Step 4 : train locally, starting from the global model
            new_parms = local_train(model["parameters"], texts, labels, epochs = epochs, seed = info["round_id"])
            
            #Step 5: upload the results
            resp = http.post(
                f"{url}/updates", 
                json={
                    "client_id": client_id,
                    "round_id": info["round_id"],
                    "model_version": info["model_version"],     #Must match, or the coordinator rejects it
                    "sample_count": len(texts),                 #becomes our weight in FedAvg
                    "parameters": new_parms,
                },
                timeout=30,
            )
            print(f"[{client_id} round {info['round_id']}: {resp.status_code} {resp.json()}]")
            last_round = info["round_id"]                       #never retry the same round
            if resp.ok:
                done += 1
        except requests.RequestException as exc:
            #Network error: coordinator may be restarting
            # Don't crash: just keeps polling until it comes back
            print(f"[{client_id}] coordinator unreachable: {exc}")
            
            
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--client-id", required=True)                        #Unique name: letter, digits
    p.add_argument("--data", required=True)                             #path to the client's csv
    p.add_argument("--coordinator", default= "http://localhost:8000")   #where the coordinator lives
    p.add_argument("--epochs", type = int, default=3)                   #local passes per round 
    p.add_argument("--max-rounds", type=int, default= 10)               #stops after this many submissions
    p.add_argument("--poll", type=float, default=1.0)                   #seconds before checks
    a = p.parse_args()
    run(a.client_id, a.data, a.coordinator,a.epochs, a.max_rounds, a.poll)
            