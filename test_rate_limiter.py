import requests
import time

# URL de ton API déployée sur Railway
API_URL = "https://rate-limit-api-production.up.railway.app"
# Nombre de requêtes à envoyer
TOTAL_REQUESTS = 15

# Intervalle entre les requêtes (en secondes)
DELAY = 1

# Header "user" pour tester par utilisateur
HEADERS = {"user": "Ahmed"}

for i in range(1, TOTAL_REQUESTS + 1):
    response = requests.get(API_URL + "/", headers=HEADERS)
    if response.status_code == 429:
        print(f"[{i}] Trop de requêtes ! Status: {response.status_code} - {response.json()['detail']}")
    else:
        print(f"[{i}] OK - Status: {response.status_code} - {response.json()}")
    time.sleep(DELAY)