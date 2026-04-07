import os
import re
import threading
import time

import redis
from dotenv import load_dotenv
from fastapi import HTTPException, Request

import config_store

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    m = re.search(r"-?\d+", str(raw))
    if m:
        return int(m.group(0))
    return default


REDIS_PORT = _env_int("REDIS_PORT", 6379)
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_URL = (os.getenv("REDIS_URL") or "").strip()

# Sans Redis local : RATE_LIMIT_BACKEND=memory (développement uniquement)
USE_MEMORY = os.getenv("RATE_LIMIT_BACKEND", "redis").lower() in (
    "memory",
    "local",
    "ram",
)

r: redis.Redis | None
if USE_MEMORY:
    r = None
elif REDIS_URL:
    r = redis.from_url(REDIS_URL, decode_responses=True)
else:
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD or None,
        decode_responses=True,
    )

_memory_lock = threading.Lock()
# Même logique sliding window que Redis : timestamps (secondes) par clé
_memory_hits: dict[str, list[int]] = {}


def _redis_unavailable_message() -> str:
    return (
        "Redis est indisponible. Vérifie REDIS_URL ou REDIS_HOST / REDIS_PORT / REDIS_PASSWORD, "
        "que le service Redis tourne, et retire RATE_LIMIT_BACKEND=memory du .env si tu veux utiliser Redis."
    )


def get_client_key(request: Request) -> str:
    user = request.headers.get("user")
    if user:
        return user
    if request.client:
        return request.client.host
    return "unknown"


def _storage_key(client_key: str) -> str:
    return f"rate:{client_key}"


def _memory_prune_and_count(key: str, window: int, now: int) -> int:
    cutoff = now - window
    with _memory_lock:
        arr = _memory_hits.setdefault(key, [])
        arr[:] = [t for t in arr if t > cutoff]
        return len(arr)


def _memory_get_usage(key: str, window: int, limit: int) -> int:
    now = int(time.time())
    return _memory_prune_and_count(key, window, now)


def get_window_usage(client_key: str) -> tuple[int, int]:
    """Retourne (count_dans_fenêtre, limite_actuelle) sans enregistrer de requête."""
    window = config_store.get_window()
    limit = config_store.get_limit()
    now = int(time.time())
    key = _storage_key(client_key)

    if USE_MEMORY:
        count = _memory_prune_and_count(key, window, now)
        return count, limit

    assert r is not None
    try:
        r.zremrangebyscore(key, 0, now - window)
        count = r.zcard(key)
    except redis.RedisError as e:
        raise HTTPException(status_code=503, detail=_redis_unavailable_message()) from e
    return count, limit


def check_rate_limit(request: Request) -> tuple[str, int, int]:
    """
    Applique la limite. Retourne (client_key, count_après_acceptation, limit).
    Lève HTTPException 429 si dépassement.
    """
    client_key = get_client_key(request)
    window = config_store.get_window()
    limit = config_store.get_limit()
    now = int(time.time())
    key = _storage_key(client_key)

    if USE_MEMORY:
        with _memory_lock:
            arr = _memory_hits.setdefault(key, [])
            cutoff = now - window
            arr[:] = [t for t in arr if t > cutoff]
            count = len(arr)
            if count >= limit:
                raise HTTPException(status_code=429, detail="Trop de requêtes")
            arr.append(now)
            new_count = len(arr)
        print(f"User/IP: {client_key} - Requests: {new_count} (memory)")
        return client_key, new_count, limit

    assert r is not None
    try:
        r.zremrangebyscore(key, 0, now - window)
        count = r.zcard(key)
        if count >= limit:
            raise HTTPException(status_code=429, detail="Trop de requêtes")

        r.zadd(key, {str(now): now})
        r.expire(key, window)
    except HTTPException:
        raise
    except redis.RedisError as e:
        raise HTTPException(status_code=503, detail=_redis_unavailable_message()) from e

    new_count = count + 1
    print(f"User/IP: {client_key} - Requests: {new_count}")
    return client_key, new_count, limit


def rate_limiter(request: Request) -> None:
    check_rate_limit(request)
