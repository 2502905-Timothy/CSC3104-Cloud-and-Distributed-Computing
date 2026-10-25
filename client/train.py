# Local training for one federated client. 
# This is the "learning" half of federated learning: each client takes the 
# current global model, improves it with its OWN private messages, and hands
# back the improved model. The raw messages never leaves the client.
#
# Start from the global model, train on local data, return the NEW full model.
#     global_parameters : the flat list downloaded from the coordinator
#     texts, labels     : this client's private messages and their labels (1 = scam)
#     epochs            : how many passes over the local data per round
#     seed              : makes the shuffling repeatable (the client passes the round number)
    


import numpy as np
from sklearn.linear_model import SGDClassifier
from shared.fed_params import CLASSES, flatten, make_vectorizer, unflatten

def local_train(global_parameters: list[float], texts, labels, epochs:int = 3, seed:int = 0) -> list[float]:
    # Step 1: turn text into numbers. Hashing needs no fitting, so transform() is enough.
    X = make_vectorizer().transform(texts)
    y = np.asarray(labels)
    
    # Step 2: split the flat global list back into weights and bias
    coef, intercept = unflatten(global_parameters)
    
    # Step 3: Create a logistic-regression classifier trained by SGD (Stochastic Gradient Descent).
    model = SGDClassifier(
        loss="log_loss",            #logistic regressino -> output scam probability
        learning_rate="constant",  # same step size every update (steadier for FedAvg)
        eta0=0.5,                   # Step size
        alpha=1e-5,                 #tiny regularisation (penalthy on large weights)
        random_state=seed,
    )
    
    # Step 4: load the GLOBAL weights into the model, so training continues from the global model rather then from scratch
    #We use partial_fit() instead of fit() because fit() refuses to run if a client only has one class locally, which is common with non-IID data
    model.classes_ = CLASSES
    model.coef_ = coef.copy()       #.copy() so we never modify the caller's data
    model.intercept_ = intercept.copy()
    
    # Step 5: train. Each partial_fit call is one pass (epoch) over the local data.
    for _ in range(epochs):
        model.partial_fit(X,y,classes=CLASSES)
    
    # Step 6: Flatten the improved weights back into a list to send to the coordinator.
    return flatten(model.coef_, model.intercept_)


# Measures how good a model is on labelled messages
# Scan is the "positive" class, so:
#     precision = of messages flagged as scam, how many really were scams
#     recall = of real scams, how many we caught
#     f1 = a single score balancing precision and recall

def evaluate(parameters: list[float], texts, labels) -> dict:
    from sklearn.metrics import f1_score, precision_score, recall_score
 
    X = make_vectorizer().transform(texts)
    coef, intercept = unflatten(parameters)
 
    # Prediction by hand: score = weights . features + bias; score > 0 means "scam".
    pred = ((X @ coef.T).ravel() + intercept[0] > 0).astype(int)
 
    # zero_division=0 avoids errors/warnings if the model predicts no scams at all.
    return {
        "precision": precision_score(labels, pred, zero_division=0),
        "recall": recall_score(labels, pred, zero_division=0),
        "f1": f1_score(labels, pred, zero_division=0),
    }