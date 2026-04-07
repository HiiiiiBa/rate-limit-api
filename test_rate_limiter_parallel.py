import requests
import threading
import time

API_URL = "https://rate-limit-api-production.up.railway.app"
TOTAL_REQUESTS = 12      # nombre de requêtes par utilisateur
DELAY = 0.5              # intervalle entre les requêtes en secondes

# Liste d'utilisateurs simulés
users = ["Ahmed", "Sara", "Ali"]

def send_requests(user):
    headers = {"user": user}
    for i in range(1, TOTAL_REQUESTS + 1):
        response = requests.get(API_URL + "/", headers=headers)
        if response.status_code == 429:
            print(f"[{user}][{i}] Trop de requêtes ! Status: {response.status_code}")
        else:
            print(f"[{user}][{i}] OK - Status: {response.status_code}")
        time.sleep(DELAY)

threads = []

# Créer un thread pour chaque utilisateur
for user in users:
    t = threading.Thread(target=send_requests, args=(user,))
    threads.append(t)
    t.start()

# Attendre que tous les threads se terminent
for t in threads:
    t.join()