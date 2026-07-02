from flask import Blueprint, jsonify, render_template
import datetime


whatsapp_v2 = Blueprint(
    "whatsapp_v2",
    __name__
)



# =====================================
# TELA PRINCIPAL
# =====================================

@whatsapp_v2.route("/central-whatsapp")
def central_whatsapp():

    return render_template(
        "comunicacao/whatsapp_v2.html"
    )





# =====================================
# STATUS
# =====================================

import requests


NODE_URL = "http://localhost:3001"



@whatsapp_v2.route("/api/whatsapp/status")
def whatsapp_status():

    try:

        resposta = requests.get(
            NODE_URL + "/status",
            timeout=3
        )


        return resposta.json()


    except:


        return {

            "status":"offline"

        }




# =====================================
# QR CODE
# =====================================


@whatsapp_v2.route(
    "/api/whatsapp/qr"
)
def whatsapp_qr():


    # temporário

    return jsonify({

        "success":True,

        "qr":None,

        "message":
        "aguardando node"

    })







# =====================================
# DESCONECTAR
# =====================================


@whatsapp_v2.route(
"/api/whatsapp/disconnect",
methods=["POST"]
)
def whatsapp_disconnect():


    return jsonify({

        "success":True,

        "message":
        "Sessão encerrada"

    })
