# Conventions shared by the coordinator and every federatd client.
# This stores the global model as one flat list of numbers and average lists of numbers


import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
#Number of text features (columns) each message is converted into, rejects updates longer than 20000 numbers, keep below 19999
N_FEATURES = 4096   
#Total length of flat parameter list: one weight per feature + 1 intercept (bias).
N_PARAMS = N_FEATURES + 1
#Two possible labels. 0 = legitimate message, 1 = scam message
CLASSES = np.array([0,1])

def make_vectorizer() -> HashingVectorizer:
    return HashingVectorizer(
        n_features= N_FEATURES,         # number of colums (must match N_FEATURES everywhere)
        ngram_range=(1,2),              # use single words and pairs of consecutive words
        lowercase=True,                 
        alternate_sign= False,          # keeps all feature value >=0 (easier to interpret)
        norm="l2",                      # scale each message vector to length 1, so long messaages do not dominate short ones
    )

def initial_parameters() -> list[float]:
    return [0.0] * N_PARAMS

# Returns a plain python list so it can be sent as JSON
def flatten(coef: np.ndarray, intercept: np.ndarray) -> list[float]:
    return [float(x)for x in np.concatenate([np.ravel(coef), np.ravel(intercept)])]

# Used when a client receives the global model from the coordinator and needs to load it into a scikit-learn classifier
def unflatten(parameters: list[float]) -> tuple[np.ndarray,np.ndarray]:
    arr = np.asarray(parameters, dtype=np.float64)
    
    # Safety check: refuse a list of the wrong length instead of silently misreading it
    if arr.shape != (N_PARAMS,):
        raise ValueError(f"Expected {N_PARAMS} parameters, got {arr.shape}")
    
    #First N_FEATURES numbers = weight(coef); the last number = bias (intercept)
    return arr[:N_FEATURES].reshape(1,N_FEATURES), arr[N_FEATURES:].reshape(1)

