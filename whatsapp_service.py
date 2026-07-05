import requests

EVOLUTION_URL = "https://zoom-leggings-viability.ngrok-free.dev"
API_KEY = "smartzen123"

# memória temporária (sem banco)
SESSOES_WHATSAPP = {}


def criar_instancia(user_id):
    instance_name = f"smartzen_{user_id}"

    res = requests.post(
        f"{EVOLUTION_URL}/instance/create",
        headers={
            "apikey": API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "instanceName": instance_name,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True
        }
    )

    data = res.json()

    SESSOES_WHATSAPP[user_id] = {
        "instance": instance_name,
        "qr": data.get("qrcode", {}).get("base64"),
        "status": "connecting"
    }

    return data


def status_instancia(user_id):
    instance = SESSOES_WHATSAPP.get(user_id, {}).get("instance")

    if not instance:
        return "not_created"

    res = requests.get(
        f"{EVOLUTION_URL}/instance/fetchInstances",
        headers={"apikey": API_KEY}
    )

    data = res.json()

    for i in data:
        if i["instance"]["instanceName"] == instance:
            return i["instance"]["status"]

    return "unknown"


def desconectar(user_id):
    instance = SESSOES_WHATSAPP.get(user_id, {}).get("instance")

    if not instance:
        return

    requests.delete(
        f"{EVOLUTION_URL}/instance/logout/{instance}",
        headers={"apikey": API_KEY}
    )

    requests.delete(
        f"{EVOLUTION_URL}/instance/delete/{instance}",
        headers={"apikey": API_KEY}
    )

    SESSOES_WHATSAPP.pop(user_id, None)
