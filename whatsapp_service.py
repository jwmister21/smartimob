import requests

EVOLUTION_URL = "http://localhost:8080"
API_KEY = "smartzen123"


def criar_instancia(nome):
    url = f"{EVOLUTION_URL}/instance/create"

    payload = {
        "instanceName": nome,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS"
    }

    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json"
    }

    return requests.post(url, json=payload, headers=headers).json()


def pegar_qrcode(nome):
    url = f"{EVOLUTION_URL}/instance/connect/{nome}"

    headers = {
        "apikey": API_KEY
    }

    return requests.get(url, headers=headers).json()
