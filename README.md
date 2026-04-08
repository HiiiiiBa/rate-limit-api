# Rate Limiting API (FastAPI + Redis) + Dashboard

Projet de **limitation de requêtes** (rate limiting) pour protéger une API contre la surcharge et les abus.

- **Backend**: FastAPI
- **Rate limiting**: par **utilisateur** (header `user`) ou **IP** (avec support `X-Forwarded-For`)
- **Blocage**: HTTP **429**
- **Stockage**:
  - **Redis** (production / Railway)
  - **Mémoire** (local, si Redis n’est pas disponible)
- **Dashboard (bonus)**: UI web `/dashboard/` + API `/api/dashboard/*` + WebSocket temps réel

## URLs (production)

- **API**: `https://rate-limit-api-production.up.railway.app`
- **Endpoint exemple**: `https://rate-limit-api-production.up.railway.app/users`
- **Dashboard**: `https://rate-limit-api-production.up.railway.app/dashboard/`

## Architecture (résumé)

Client → FastAPI → **Middleware** (`main.py`) → `rate_limiter.check_rate_limit()`  
- Si OK → endpoint → réponse 200/…  
- Si dépassement → **429**  

Stockage des hits:
- **Redis** (sorted set + fenêtre glissante) si `REDIS_URL` est présent (prod)
- **Mémoire** (liste de timestamps) si `RATE_LIMIT_BACKEND=memory` (local)

Dashboard:
- FastAPI sert des statiques React depuis `static/dashboard/`
- WebSocket `/api/dashboard/ws` pousse un snapshot toutes les 1s

## Lancer en local

### 1) Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2) Variables d’environnement (local)

Option A — **Sans Redis** (le plus simple): ajoute dans `.env`

```env
RATE_LIMIT_BACKEND=memory
LIMIT=10
WINDOW=60
```

Option B — **Avec Redis local**: configure `.env`

```env
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
LIMIT=10
WINDOW=60
```

### 3) Lancer l’API

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Puis:
- `http://127.0.0.1:8000/users`
- `http://127.0.0.1:8000/dashboard/`

## Dashboard (front)

Le dashboard est un front React buildé dans `static/dashboard/`.

Rebuild local si tu modifies `frontend/`:

```bash
cd frontend
npm install
npm run build
```

## Variables d’environnement (production / Railway)

Dans **Railway → Service API → Variables**:

- **Redis recommandé**:
  - `REDIS_URL=${{Redis.REDIS_URL}}` (référence au service Redis)
- Ne pas définir `RATE_LIMIT_BACKEND=memory` en production (sinon rate limiting par instance).
- `LIMIT` et `WINDOW` pour régler le quota global.
- Optionnel: `LOG_LEVEL=INFO` et `CORS_ORIGINS=https://ton-site,...`

## Exemple de test rate limit (429)

Envoie plus de `LIMIT` requêtes dans la fenêtre `WINDOW`:

```powershell
1..15 | ForEach-Object { curl.exe -s -w " HTTP:%{http_code}`n" https://rate-limit-api-production.up.railway.app/users }
```

Test par utilisateur (header `user`):

```powershell
1..12 | ForEach-Object { curl.exe -s -H "user: Ahmed" -w " HTTP:%{http_code}`n" https://rate-limit-api-production.up.railway.app/ }
```

## Tests (pytest)

```bash
pytest -q
```

Les tests forcent le backend **mémoire** pour être reproductibles sans Redis.

