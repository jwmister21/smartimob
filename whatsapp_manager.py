import os
import requests
from datetime import datetime


class WhatsAppManager:
    """
    Gerenciador de integração com Evolution API
    SMARTZEN IMOB
    """

    def __init__(self, get_db):

        self.get_db = get_db

        self.base_url = os.getenv("EVOLUTION_URL", "").rstrip("/")
        self.api_key = os.getenv("EVOLUTION_API_KEY")

        if not self.base_url:
            raise Exception("EVOLUTION_URL não configurada.")

        if not self.api_key:
            raise Exception("EVOLUTION_API_KEY não configurada.")

    # ==========================================================
    # REQUEST PADRÃO
    # ==========================================================

    def _request(self, method, endpoint, payload=None):

        url = f"{self.base_url}{endpoint}"

        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json"
        }

        print("\n" + "=" * 70)
        print("EVOLUTION API")
        print("METHOD :", method)
        print("URL    :", url)
        print("PAYLOAD:", payload)
        print("=" * 70)

        try:

            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=payload,
                timeout=60
            )

            try:
                body = response.json()
            except Exception:
                body = response.text

            print("STATUS :", response.status_code)
            print("BODY   :", body)

            return {
                "success": response.status_code in [200, 201],
                "status": response.status_code,
                "body": body
            }

        except Exception as e:

            print("ERRO:", repr(e))

            return {
                "success": False,
                "status": 500,
                "body": str(e)
            }

    # ==========================================================
    # BANCO DE DADOS
    # ==========================================================

    def buscar_sessao(self, usuario_id):

        conn = self.get_db()

        sessao = conn.execute("""

            SELECT *

            FROM whatsapp_sessoes

            WHERE usuario_id=?

        """, (usuario_id,)).fetchone()

        conn.close()

        return sessao


    def salvar_sessao(
        self,
        usuario_id,
        instance_name,
        instance_id=None,
        status="DISCONNECTED"
    ):

        conn = self.get_db()

        existe = conn.execute("""

            SELECT id

            FROM whatsapp_sessoes

            WHERE usuario_id=?

        """, (usuario_id,)).fetchone()

        if existe:

            conn.execute("""

                UPDATE whatsapp_sessoes

                SET

                    instance_name=?,
                    instance_id=?,
                    status=?,
                    updated_at=CURRENT_TIMESTAMP

                WHERE usuario_id=?

            """, (

                instance_name,
                instance_id,
                status,
                usuario_id

            ))

        else:

            conn.execute("""

                INSERT INTO whatsapp_sessoes(

                    usuario_id,
                    instance_name,
                    instance_id,
                    status

                )

                VALUES(?,?,?,?)

            """, (

                usuario_id,
                instance_name,
                instance_id,
                status

            ))

        conn.commit()
        conn.close()


    def atualizar_status(self, usuario_id, status):

        conn = self.get_db()

        conn.execute("""

            UPDATE whatsapp_sessoes

            SET

                status=?,
                updated_at=CURRENT_TIMESTAMP

            WHERE usuario_id=?

        """, (

            status,
            usuario_id

        ))

        conn.commit()
        conn.close()


    def obter_instance_name(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:
            return None

        return sessao["instance_name"]

      # ==========================================================
    # INSTÂNCIAS
    # ==========================================================

    def criar_instancia(self, usuario_id):

        instance_name = f"smartzen_usuario_{usuario_id}"

        resposta = self._request(
            "POST",
            "/instance/create",
            {
                "instanceName": instance_name,
                "integration": "WHATSAPP-BAILEYS",
                "qrcode": True
            }
        )

        if not resposta["success"]:
            return resposta

        data = resposta["body"]

        instance_id = None

        try:

            if isinstance(data, dict):

                if "instance" in data:

                    if isinstance(data["instance"], dict):

                        instance_id = data["instance"].get("instanceId")

        except Exception:
            pass

        self.salvar_sessao(
            usuario_id=usuario_id,
            instance_name=instance_name,
            instance_id=instance_id,
            status="CREATED"
        )

        return resposta

    # ----------------------------------------------------------

    def listar_instancias(self):

        return self._request(
            "GET",
            "/instance/fetchInstances"
        )

    # ----------------------------------------------------------

    def buscar_status(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        resposta = self.listar_instancias()

        if not resposta["success"]:
            return resposta

        dados = resposta["body"]

        if not isinstance(dados, list):

            return {
                "success": False,
                "body": "Resposta inválida."
            }

        for item in dados:

            try:

                if item["instance"]["instanceName"] == instance:

                    status = item["instance"]["status"]

                    self.atualizar_status(
                        usuario_id,
                        status
                    )

                    return {
                        "success": True,
                        "status": status
                    }

            except Exception:
                continue

        return {
            "success": False,
            "body": "Instância não localizada."
        }

    # ----------------------------------------------------------

    def excluir_instancia(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        resposta = self._request(
            "DELETE",
            f"/instance/delete/{instance}"
        )

        if resposta["success"]:

            conn = self.get_db()

            conn.execute("""

                DELETE FROM whatsapp_sessoes

                WHERE usuario_id=?

            """, (usuario_id,))

            conn.commit()
            conn.close()

        return resposta

    # ----------------------------------------------------------

    def logout(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        resposta = self._request(
            "DELETE",
            f"/instance/logout/{instance}"
        )

        if resposta["success"]:

            self.atualizar_status(
                usuario_id,
                "DISCONNECTED"
            )

        return resposta

    # ==========================================================
    # ENVIO DE MENSAGENS
    # ==========================================================

    def send_text(self, usuario_id, numero, texto):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:
            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        payload = {
            "number": numero,
            "text": texto
        }

        resposta = self._request(
            "POST",
            f"/message/sendText/{instance}",
            payload
        )

        if resposta["success"]:

            conn = self.get_db()

            conn.execute("""

                UPDATE whatsapp_sessoes

                SET

                    last_connection=CURRENT_TIMESTAMP,
                    last_error=NULL,
                    updated_at=CURRENT_TIMESTAMP

                WHERE usuario_id=?

            """, (usuario_id,))

            conn.commit()
            conn.close()

        else:

            conn = self.get_db()

            conn.execute("""

                UPDATE whatsapp_sessoes

                SET

                    last_error=?,
                    updated_at=CURRENT_TIMESTAMP

                WHERE usuario_id=?

            """, (

                str(resposta["body"]),
                usuario_id

            ))

            conn.commit()
            conn.close()

        return resposta


    # ----------------------------------------------------------

    def send_image(
        self,
        usuario_id,
        numero,
        image_url,
        caption=""
    ):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        payload = {

            "number": numero,

            "mediatype": "image",

            "media": image_url,

            "caption": caption

        }

        return self._request(
            "POST",
            f"/message/sendMedia/{instance}",
            payload
        )


    # ----------------------------------------------------------

    def send_document(
        self,
        usuario_id,
        numero,
        document_url,
        filename="arquivo.pdf"
    ):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        payload = {

            "number": numero,

            "mediatype": "document",

            "media": document_url,

            "fileName": filename

        }

        return self._request(
            "POST",
            f"/message/sendMedia/{instance}",
            payload
        )


    # ----------------------------------------------------------

    def send_audio(
        self,
        usuario_id,
        numero,
        audio_url
    ):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        payload = {

            "number": numero,

            "mediatype": "audio",

            "media": audio_url

        }

        return self._request(
            "POST",
            f"/message/sendMedia/{instance}",
            payload
        )

    # ==========================================================
    # SINCRONIZAR INSTÂNCIAS
    # ==========================================================

    def sincronizar_instancias(self):

        resposta = self.listar_instancias()

        if not resposta["success"]:
            return resposta

        instancias = resposta["body"]

        if not isinstance(instancias, list):
            return {
                "success": False,
                "body": "Resposta inválida da Evolution."
            }

        conn = self.get_db()

        atualizadas = 0

        for item in instancias:

            try:

                instance = item.get("instance", {})

                instance_name = instance.get("instanceName")
                status = instance.get("status")

                if not instance_name:
                    continue

                conn.execute("""

                    UPDATE whatsapp_sessoes

                    SET

                        status=?,
                        updated_at=CURRENT_TIMESTAMP

                    WHERE instance_name=?

                """, (

                    status,
                    instance_name

                ))

                atualizadas += 1

            except Exception as e:

                print("Erro sincronizando:", e)

        conn.commit()
        conn.close()

        return {
            "success": True,
            "sincronizadas": atualizadas
        }

    # ==========================================================
    # BUSCAR QR CODE
    # ==========================================================

    def buscar_qr(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        resposta = self._request(
            "GET",
            f"/instance/connect/{instance}"
        )

        return resposta

    # ==========================================================
    # RECONECTAR
    # ==========================================================

    def conectar(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        instance = sessao["instance_name"]

        return self._request(
            "GET",
            f"/instance/connect/{instance}"
        )

    # ==========================================================
    # TESTAR CONEXÃO
    # ==========================================================

    def ping(self):

        return self._request(
            "GET",
            "/instance/fetchInstances"
        )


    # ==========================================================
    # VERIFICAR SE A INSTÂNCIA EXISTE
    # ==========================================================

    def instancia_existe(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:
            return False

        resposta = self.listar_instancias()

        if not resposta["success"]:
            return False

        instance = sessao["instance_name"]

        for item in resposta["body"]:

            try:

                if item["instance"]["instanceName"] == instance:
                    return True

            except:
                pass

        return False

    # ==========================================================
    # INFORMAÇÕES DA INSTÂNCIA
    # ==========================================================

    def info_instancia(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:

            return {
                "success": False,
                "body": "Sessão não encontrada."
            }

        resposta = self.listar_instancias()

        if not resposta["success"]:
            return resposta

        instance = sessao["instance_name"]

        for item in resposta["body"]:

            try:

                if item["instance"]["instanceName"] == instance:

                    return {
                        "success": True,
                        "instance": item
                    }

            except:
                pass

        return {
            "success": False,
            "body": "Instância não encontrada."
        }

    # ==========================================================
    # REMOVER SESSÃO DO BANCO
    # ==========================================================

    def remover_sessao(self, usuario_id):

        conn = self.get_db()

        conn.execute("""

            DELETE FROM whatsapp_sessoes

            WHERE usuario_id=?

        """, (usuario_id,))

        conn.commit()
        conn.close()

        return True

    # ==========================================================
    # DADOS DA SESSÃO
    # ==========================================================

    def get_status(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:
            return None

        return sessao["status"]


    def get_phone(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:
            return None

        return sessao["phone"]


    def get_profile_name(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:
            return None

        return sessao["profile_name"]


    def get_profile_picture(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        if not sessao:
            return None

        return sessao["profile_picture"]


    # ==========================================================
    # ATUALIZAR DADOS DA SESSÃO
    # ==========================================================

    def atualizar_dados(
        self,
        usuario_id,
        profile_name=None,
        profile_picture=None,
        phone=None
    ):

        conn = self.get_db()

        conn.execute("""

            UPDATE whatsapp_sessoes

            SET

                profile_name=?,
                profile_picture=?,
                phone=?,
                updated_at=CURRENT_TIMESTAMP

            WHERE usuario_id=?

        """, (

            profile_name,
            profile_picture,
            phone,
            usuario_id

        ))

        conn.commit()
        conn.close()

        return True


    # ==========================================================
    # EXISTE SESSÃO?
    # ==========================================================

    def possui_sessao(self, usuario_id):

        sessao = self.buscar_sessao(usuario_id)

        return sessao is not None


    # ==========================================================
    # RESETAR SESSÃO
    # ==========================================================

    def resetar_sessao(self, usuario_id):

        conn = self.get_db()

        conn.execute("""

            UPDATE whatsapp_sessoes

            SET

                status='DISCONNECTED',
                profile_name=NULL,
                profile_picture=NULL,
                phone=NULL,
                last_error=NULL,
                updated_at=CURRENT_TIMESTAMP

            WHERE usuario_id=?

        """, (usuario_id,))

        conn.commit()
        conn.close()

        return True
