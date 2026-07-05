import requests

EVOLUTION_URL = "https://zoom-leggings-viability.ngrok-free.dev"
API_KEY = "smartzen123"

# memória temporária (sem banco)
SESSOES_WHATSAPP = {}


# =========================
# CRIAR INSTÂNCIA
# =========================
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

    # valida erro
    if res.status_code != 200:
        return {"error": True, "response": data}

    SESSOES_WHATSAPP[user_id] = {
        "instance": instance_name,
        "status": "connecting"
    }

    return data


# =========================
# STATUS
# =========================
def status_instancia(user_id):

    instance = SESSOES_WHATSAPP.get(user_id, {}).get("instance")

    if not instance:
        return "not_created"

    res = requests.get(
        f"{EVOLUTION_URL}/instance/fetchInstances",
        headers={"apikey": API_KEY}
    )

    if res.status_code != 200:
        return "error"

    data = res.json()

    for i in data:
        if i["instance"]["instanceName"] == instance:
            return i["instance"]["status"]

    return "unknown"


# =========================
# DESCONECTAR / DELETE
# =========================
def desconectar(user_id):

    instance = SESSOES_WHATSAPP.get(user_id, {}).get("instance")

    if not instance:
        return

    try:
        requests.delete(
            f"{EVOLUTION_URL}/instance/logout/{instance}",
            headers={"apikey": API_KEY}
        )

        requests.delete(
            f"{EVOLUTION_URL}/instance/delete/{instance}",
            headers={"apikey": API_KEY}
        )

    except Exception as e:
        print("Erro ao desconectar:", e)

    SESSOES_WHATSAPP.pop(user_id, None)


# =========================
# ENVIAR MENSAGEM (IMPORTANTE)
# =========================
def enviar_mensagem(user_id, numero, mensagem):

    instance = SESSOES_WHATSAPP.get(user_id, {}).get("instance")

    if not instance:
        return {"error": "instancia_nao_existe"}

    res = requests.post(
        f"{EVOLUTION_URL}/message/sendText/{instance}",
        headers={
            "apikey": API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "number": numero,
            "text": mensagem
        }
    )

    return res.json()
