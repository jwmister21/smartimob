import requests

EVOLUTION_URL = "https://zoom-leggings-viability.ngrok-free.dev"
API_KEY = "smartzen123"

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
        "instance": instance_name
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


def enviar_mensagem(user_id, numero, texto):

    instance = SESSOES_WHATSAPP.get(user_id, {}).get("instance")

    if not instance:
        return {
            "success": False,
            "erro": "Instância não encontrada."
        }

    print("ENVIANDO PARA:", instance)

    resposta = requests.post(
        f"{EVOLUTION_URL}/message/sendText/{instance}",
        headers={
            "apikey": API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "number": numero,
            "text": texto
        }
    )

    print("STATUS:", resposta.status_code)
    print("BODY:", resposta.text)

    return {
        "success": resposta.status_code in [200, 201],
        "status": resposta.status_code,
        "body": resposta.text
    }
