import sqlite3
import math
import requests

DB_PATH = "COLOQUE_O_MESMO_DB_PATH_DO_APP"


HEADERS = {
    "User-Agent": "SMARTZEN IMOB"
}


def distancia(lat1, lon1, lat2, lon2):

    R = 6371000

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return int(
        R * 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


def buscar_coordenadas(rua, bairro, cidade, cep):

    endereco = f"{rua}, {bairro}, {cidade}, {cep}, Brasil"

    r = requests.get(

        "https://nominatim.openstreetmap.org/search",

        params={

            "q": endereco,

            "format": "jsonv2",

            "limit": 1

        },

        headers=HEADERS,

        timeout=20

    )

    dados = r.json()

    if len(dados) == 0:
        return None

    return (

        float(dados[0]["lat"]),

        float(dados[0]["lon"])

    )
