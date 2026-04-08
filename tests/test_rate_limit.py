import importlib
import os

import pytest
from fastapi.testclient import TestClient


def _make_client(limit: int = 3, window: int = 60) -> TestClient:
    # Forcer le backend mémoire pour des tests reproductibles (pas besoin de Redis).
    os.environ["RATE_LIMIT_BACKEND"] = "memory"
    os.environ["LIMIT"] = str(limit)
    os.environ["WINDOW"] = str(window)

    import config_store
    import main
    import rate_limiter

    importlib.reload(config_store)
    importlib.reload(rate_limiter)
    importlib.reload(main)

    # Appliquer les limites dynamiques (config_store charge l'env au reload).
    config_store.set_limit(limit)
    config_store.set_window(window)

    # Reset des hits mémoire entre tests.
    with rate_limiter._memory_lock:  # noqa: SLF001
        rate_limiter._memory_hits.clear()  # noqa: SLF001

    return TestClient(main.app)


def test_under_limit_returns_200():
    client = _make_client(limit=3)
    r1 = client.get("/users")
    r2 = client.get("/users")
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_exceed_limit_returns_429():
    client = _make_client(limit=3)
    for _ in range(3):
        assert client.get("/users").status_code == 200
    r = client.get("/users")
    assert r.status_code == 429
    assert r.json()["detail"]


def test_user_header_isolated_buckets():
    client = _make_client(limit=2)
    # Ahmed atteint sa limite
    assert client.get("/users", headers={"user": "Ahmed"}).status_code == 200
    assert client.get("/users", headers={"user": "Ahmed"}).status_code == 200
    assert client.get("/users", headers={"user": "Ahmed"}).status_code == 429

    # Sara a son propre compteur
    assert client.get("/users", headers={"user": "Sara"}).status_code == 200


def test_x_forwarded_for_used_as_ip_key_when_no_user_header():
    client = _make_client(limit=2)
    h = {"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
    assert client.get("/users", headers=h).status_code == 200
    assert client.get("/users", headers=h).status_code == 200
    assert client.get("/users", headers=h).status_code == 429

