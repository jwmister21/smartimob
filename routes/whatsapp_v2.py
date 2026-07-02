from flask import Blueprint, jsonify, render_template
import requests



whatsapp_v2 = Blueprint(
    "whatsapp_v2",
    __name__
)


import os

NODE_URL = os.getenv(
    "WHATSAPP_NODE_URL",
    "http://localhost:3001"
)




@whatsapp_v2.route("/central-whatsapp")
def central_whatsapp():

    return render_template(
        "comunicacao/whatsapp_v2.html"
    )






@whatsapp_v2.route("/api/whatsapp/status")
def whatsapp_status():


    try:

        resposta = requests.get(
            NODE_URL + "/status",
            timeout=3
        )


        return jsonify(
            resposta.json()
        )


    except Exception as e:


        return jsonify({

            "status":"offline",

            "error":
            str(e)

        })








@whatsapp_v2.route("/api/whatsapp/qr")
def whatsapp_qr():


    try:


        resposta = requests.get(
            NODE_URL + "/qr",
            timeout=3
        )


        return jsonify(
            resposta.json()
        )


    except:


        return jsonify({

            "qr":None,

            "status":"offline"

        })









@whatsapp_v2.route(
"/api/whatsapp/disconnect",
methods=["POST"]
)
def disconnect():


    try:


        resposta = requests.post(
            NODE_URL + "/disconnect",
            timeout=5
        )


        return jsonify(
            resposta.json()
        )


    except:


        return jsonify({

            "success":False,

            "message":
            "Node offline"

        })
