import time
from fastapi import Request, HTTPException

requests = {}

LIMIT = 10
WINDOW = 60

def rate_limiter(request: Request):
    
    # priorité utilisateur
    user = request.headers.get("user")
    
    if user:
        key = user
    else:
        key = request.client.host

    now = time.time()

    if key not in requests:
        requests[key] = []

    requests[key] = [t for t in requests[key] if now - t < WINDOW]

    if len(requests[key]) >= LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Trop de requêtes"
        )

    requests[key].append(now)

    print(f"User/IP: {key} - Requests: {len(requests[key])}")