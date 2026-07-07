import os
import sqlite3
import secrets
import requests 
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.utils import secure_filename
from google import genai
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from whatsapp_manager import WhatsAppManager
from moviepy.video.VideoClip import ColorClip 
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.VideoClip import TextClip
from moviepy.audio.io.AudioFileClip import AudioFileClip 
from moviepy.video.VideoClip import ImageClip# Se precisar de outros, adicione aqui
from moviepy import concatenate_videoclips
from routes.whatsapp_v2 import whatsapp_v2
import google.generativeai as genai
import json
import pdfplumber
import re
from openai import OpenAI
from flask import send_from_directory
from flask_socketio import SocketIO
import pandas as pd
import base64
from pypdf import PdfReader
import gdown
import uuid


app = Flask(__name__)
app.register_blueprint(whatsapp_v2)
socketio = SocketIO(app, cors_allowed_origins="*")
DB_DIR = "/data"

UPLOAD_FOLDER_IMOVEIS = "/data/uploads/imoveis"
 
os.makedirs(UPLOAD_FOLDER_IMOVEIS, exist_ok=True)

app.config['UPLOAD_FOLDER_IMOVEIS'] = UPLOAD_FOLDER_IMOVEIS
app.config['UPLOAD_FOLDER_PERFIL'] = 'static/uploads/perfil'
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
# O modelo Flash atual é o 'gemini-1.5-flash'
model = genai.GenerativeModel('gemini-2.5-flash')
app.secret_key = 'uma_chave_muito_secreta_e_unica'
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"), # Pegue em console.groq.com
    base_url="https://api.groq.com/openai/v1"
)


# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Banco persistente no Volume Railway
DB_DIR = "/data"
os.makedirs(DB_DIR, exist_ok=True)

DB_PATH = os.path.join(DB_DIR, "imobiliaria.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Inicialização do Banco
def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios 
                    (id INTEGER PRIMARY KEY, nome TEXT, email TEXT UNIQUE, senha TEXT, empresa_id INTEGER, is_admin INTEGER)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS clientes 
                    (id INTEGER PRIMARY KEY, nome TEXT, telefone TEXT, empresa_id INTEGER)''')
    conn.commit()
    conn.close()

# Roda a inicialização ao subir
init_db()

api_key = os.getenv('GCP_API_KEY')

@app.context_processor
def injetar_lembretes():

    if "usuario_id" not in session:
        return dict(lembretes=[])

    hoje = datetime.now().strftime("%Y-%m-%d")

    conn = get_db()

    lembretes = conn.execute("""
        SELECT *
        FROM clientes
        WHERE date(data_visita) = ?
          AND empresa_id = ?
    """, (
        hoje,
        session["usuario_id"]
    )).fetchall()

    conn.close()

    return dict(lembretes=lembretes)
 
 

whatsapp = WhatsAppManager(get_db)

def limpar_prefixo_fotos_func():

    import os

    pasta = app.config['UPLOAD_FOLDER_IMOVEIS']


    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()


    cursor.execute("""
        SELECT id, nome_arquivo
        FROM fotos_imoveis
    """)

    fotos = cursor.fetchall()

    total = 0


    for foto_id, nome in fotos:

        antigo = os.path.join(
            pasta,
            nome
        )


        if not os.path.exists(antigo):
            continue


        partes = nome.split("_")


        # 68_1782103932_33_1781639570_foto.jpg
        if len(partes) >= 5:

            novo_nome = "_".join(partes[2:])


            novo = os.path.join(
                pasta,
                novo_nome
            )


            if os.path.exists(novo):
                continue


            os.rename(
                antigo,
                novo
            )


            cursor.execute("""
                UPDATE fotos_imoveis
                SET nome_arquivo = ?
                WHERE id = ?
            """,
            (
                novo_nome,
                foto_id
            ))


            total += 1


    conn.commit()
    conn.close()


    print(
        "ARQUIVOS LIMPOS:",
        total
    )

def get_usuario_logado():
    from flask import session
    return session.get("usuario_id")

def get_usuario():
    usuario_id = get_usuario_logado()

    cursor.execute("""
        SELECT * FROM usuarios WHERE id = %s
    """, (usuario_id,))

    return cursor.fetchone()













@app.route("/limpar_prefixo_fotos")
def limpar_prefixo_fotos_rota():

    limpar_prefixo_fotos_func()

    return "Fotos limpas"


def limpar_imovel(imovel):
    print(f"DEBUG: Limpando imovel: {imovel.get('titulo')}")
    
    rua = imovel.get("rua", "")
    if "✓" in rua or "CHAVES" in rua or "metros" in rua.lower():
        print(f"DEBUG: Rua descartada: {rua}")
        imovel["rua"] = ""

    bairro = imovel.get("bairro", "")
    if bairro == "Forte":
        print("DEBUG: Bairro corrigido para Canto do Forte")
        imovel["bairro"] = "Canto do Forte"

    vaga = imovel.get("vaga", "")
    if vaga:
        imovel["vaga"] = vaga.replace("0", "", 1)

    if not imovel.get("valor"):
        print(f"DEBUG: Valor não encontrado para {imovel.get('titulo')}")
        imovel["valor"] = "Consultar"

    return imovel

def extrair_imoveis(texto):
    imoveis = []
    blocos = texto.split("ED.")
    print(f"DEBUG: Total de blocos encontrados: {len(blocos)-1}")
    
    for i, bloco in enumerate(blocos[1:], 1):
        bloco = bloco.strip()
        if not bloco:
            continue

        linhas = bloco.split("\n")
        titulo = "ED. " + linhas[0].strip()

        if "Tabela de imóveis" in titulo:
            print(f"DEBUG: Bloco {i} ignorado (Tabela)")
            continue

        # VALOR
        valores = re.findall(r'R\$\s*([\d\.\,]+)', bloco)
        valor = ""
        for v in valores:
            try:
                numero = float(v.replace(".", "").replace(",", "."))
                if numero > 10000:
                    valor = v
                    break
            except:
                pass
        if not valor:
            print(f"DEBUG: Bloco {i} ({titulo}) - Valor não capturado")

        # QUARTOS
        m = re.search(r'(\d+)\s*DORMIT', bloco, re.IGNORECASE)
        quartos = m.group(1) if m else ""

        # ÁREA
        m = re.search(r'(\d+)m²', bloco)
        area = m.group(1) if m else ""

        # RUA
        rua = ""
        for linha in linhas:
            if "Rua" in linha or "Av." in linha:
                rua = linha.strip()
                break
        if not rua:
            print(f"DEBUG: Bloco {i} ({titulo}) - Rua não encontrada")

        # BAIRRO
        m = re.search(r',\s*(.*?)\s*-\s*Praia Grande', bloco)
        bairro = m.group(1) if m else ""

        # CONDOMINIO
        m = re.search(r'Condomínio\s*R\$\s*([\d\.\,]+)', bloco, re.IGNORECASE)
        condominio = m.group(1) if m else ""

        # IPTU
        m = re.search(r'IPTU\s*R\$\s*([\d\.\,]+)', bloco, re.IGNORECASE)
        iptu = m.group(1) if m else ""

        # VAGA
        m = re.search(r'(\d+)\s*vaga', bloco, re.IGNORECASE)
        vaga = m.group(1) if m else ""

        imoveis.append({
            "titulo": titulo, "valor": valor, "quartos": quartos,
            "area": area, "rua": rua, "bairro": bairro,
            "condominio": condominio, "iptu": iptu, "vaga": vaga
        })

    print(f"DEBUG: Total de imóveis extraídos com sucesso: {len(imoveis)}")
    return [limpar_imovel(i) for i in imoveis]

def extrair_links_pdf(caminho):

    from pypdf import PdfReader

    links = []

    reader = PdfReader(caminho)


    for pagina in reader.pages:


        if "/Annots" not in pagina:
            continue


        for anotacao in pagina["/Annots"]:

            obj = anotacao.get_object()


            if obj.get("/A"):

                uri = obj["/A"].get("/URI")


                if uri and "drive.google.com" in str(uri):

                    links.append(str(uri))


    return links

from functools import wraps
from flask import session, flash, redirect, url_for

def somente_ceo(func):

    @wraps(func)

    def wrapper(*args, **kwargs):

        if "usuario_id" not in session:
            return redirect(url_for("login"))

        if session.get("perfil") != "CEO":

            flash("Você não possui permissão para acessar esta área.", "danger")

            return redirect(url_for("dashboard_v2"))

        return func(*args, **kwargs)

    return wrapper


def verificar_sessao(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect("/login")

        return f(*args, **kwargs)

    return decorated_function
# ... (seus imports e DB_NAME = 'seu_banco.db')

def init_db():


    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Tabela de empresas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL
        )
    """)

    # 2. Tabela de usuários
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            empresa_id INTEGER,
            status_assinatura TEXT DEFAULT 'ativo',
            session_token TEXT,
            FOREIGN KEY(empresa_id) REFERENCES empresas(id)
        )
    """)

    # 3. Tabela de clientes (A que faltava!)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT,
            email TEXT,
            empresa_id INTEGER,
            FOREIGN KEY(empresa_id) REFERENCES empresas(id)
        )
    """)

    # 4. Tabela de imóveis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imoveis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT,
            empresa_id INTEGER,
            FOREIGN KEY(empresa_id) REFERENCES empresas(id)
        )
    """)

    # Adicione isso logo antes do seu cursor.execute no app.py
    cursor.execute("PRAGMA table_info(imoveis)")
    colunas_reais = cursor.fetchall()
    print("Colunas reais no banco:", colunas_reais)

# Verifica as colunas da tabela clientes
    cursor.execute("PRAGMA table_info(clientes)")
    colunas_clientes = [c[1] for c in cursor.fetchall()]
    if "data_visita" not in colunas_clientes:
        cursor.execute("ALTER TABLE clientes ADD COLUMN data_visita TEXT")

    

    # 3. Migração da tabela USUARIOS (É aqui que estava o erro!)
    cursor.execute("PRAGMA table_info(usuarios)")
    colunas_usuarios = [c[1] for c in cursor.fetchall()]
    
    if "status_assinatura" not in colunas_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN status_assinatura TEXT DEFAULT 'ativo'")
        
    if "session_token" not in colunas_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN session_token TEXT")


    cursor.execute("PRAGMA table_info(imoveis)")
    colunas_imoveis = [c[1] for c in cursor.fetchall()]
    
    colunas_novas = ["cidade", "bairro", "rua", "iptu"]
    
    for coluna in colunas_novas:
        if coluna not in colunas_imoveis:
            cursor.execute(f"ALTER TABLE imoveis ADD COLUMN {coluna} TEXT")

    cursor.execute("PRAGMA table_info(clientes)")
    colunas_clientes = [c[1] for c in cursor.fetchall()]
    
    # Lista de colunas necessárias na tabela clientes
    colunas_necessarias = ["email", "interesse", "faixa_preco", "bairro", "data_visita"]
    
    for coluna in colunas_necessarias:
        if coluna not in colunas_clientes:
            # Adiciona a coluna se ela não existir
            cursor.execute(f"ALTER TABLE clientes ADD COLUMN {coluna} TEXT")
            print(f"Coluna {coluna} adicionada à tabela clientes.")

    conn.commit()
    conn.close()
    print("Banco de dados atualizado com sucesso!")
    print(f"Banco utilizado: {DB_PATH}")

def get_usuario():

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nome, email, empresa_id, whatsapp_sessao
        FROM usuarios
        WHERE id = ?
    """, (usuario_id,))

    usuario = cursor.fetchone()

    conn.close()

    if not usuario:
        return None

    return {
        "id": usuario["id"],
        "nome": usuario["nome"],
        "email": usuario["email"],
        "empresa_id": usuario["empresa_id"],
        "whatsapp_sessao": usuario["whatsapp_sessao"]
    }

def baixar_fotos_drive(link, imovel_id):

    import os
    import shutil
    import gdown
    from datetime import datetime
    from werkzeug.utils import secure_filename


    pasta_final = app.config['UPLOAD_FOLDER_IMOVEIS']


    os.makedirs(
        pasta_final,
        exist_ok=True
    )


    pasta_temp = os.path.join(
        pasta_final,
        f"temp_{imovel_id}"
    )


    os.makedirs(
        pasta_temp,
        exist_ok=True
    )


    print(
        "BAIXANDO DRIVE:",
        link
    )


    try:

        gdown.download_folder(
            url=link,
            output=pasta_temp,
            quiet=False
        )


    except Exception as e:

        print(
            "ERRO DRIVE (IGNORADO):",
            e
        )



    fotos = []


    # varre o que conseguiu baixar

    for raiz, diretorios, arquivos in os.walk(pasta_temp):


        for arquivo in arquivos:


            if not arquivo.lower().endswith(
                (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp"
                )
            ):
                continue



            origem = os.path.join(
                raiz,
                arquivo
            )


            novo_nome = (
                f"{imovel_id}_"
                f"{int(datetime.now().timestamp())}_"
                f"{secure_filename(arquivo)}"
            )


            destino = os.path.join(
                pasta_final,
                novo_nome
            )


            shutil.move(
                origem,
                destino
            )


            fotos.append(
                novo_nome
            )


            print(
                "FOTO SALVA:",
                novo_nome
            )



    shutil.rmtree(
        pasta_temp,
        ignore_errors=True
    )


    print(
        "TOTAL FOTOS:",
        len(fotos)
    )


    return fotos
     
def atualizar_banco():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    comandos = [

        # USUÁRIOS
        "ALTER TABLE usuarios ADD COLUMN foto_url TEXT",
        "ALTER TABLE usuarios ADD COLUMN cargo TEXT DEFAULT 'Corretor'",
        "ALTER TABLE usuarios ADD COLUMN is_admin INTEGER DEFAULT 0",
        "ALTER TABLE usuarios ADD COLUMN validade_assinatura TEXT",

        # CLIENTES
        "ALTER TABLE clientes ADD COLUMN interesse TEXT",
        "ALTER TABLE clientes ADD COLUMN faixa_preco TEXT",
        "ALTER TABLE clientes ADD COLUMN bairro TEXT",
        "ALTER TABLE clientes ADD COLUMN status_funil TEXT DEFAULT 'Lead Novo'",
        "ALTER TABLE clientes ADD COLUMN cpf TEXT",
        "ALTER TABLE clientes ADD COLUMN endereco TEXT",
        "ALTER TABLE clientes ADD COLUMN usuario_id INTEGER",

        # IMÓVEIS
        "ALTER TABLE imoveis ADD COLUMN tipo TEXT",
        "ALTER TABLE imoveis ADD COLUMN valor TEXT",
        "ALTER TABLE imoveis ADD COLUMN cidade TEXT",
        "ALTER TABLE imoveis ADD COLUMN bairro TEXT",
        "ALTER TABLE imoveis ADD COLUMN quartos INTEGER",
        "ALTER TABLE imoveis ADD COLUMN banheiros INTEGER",
        "ALTER TABLE imoveis ADD COLUMN area TEXT",
        "ALTER TABLE imoveis ADD COLUMN status TEXT",
        "ALTER TABLE imoveis ADD COLUMN descricao TEXT",
        "ALTER TABLE imoveis ADD COLUMN foto TEXT",
        "ALTER TABLE imoveis ADD COLUMN usuario_id INTEGER",

    ]

    for sql in comandos:
        try:
            cursor.execute(sql)
            print(f"OK: {sql}")
        except sqlite3.OperationalError:
            pass

    # TABELA DE FOTOS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fotos_imoveis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imovel_id INTEGER,
        nome_arquivo TEXT,
        FOREIGN KEY(imovel_id) REFERENCES imoveis(id)
    )
    """)

    conn.commit()
    conn.close()

    print("Banco atualizado com sucesso!")


init_db()
atualizar_banco()


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Supondo que você salve o is_admin na sessão durante o login
        if session.get('is_admin') != 1:
            return "Acesso Negado: Apenas administradores.", 403
        return f(*args, **kwargs)
    return decorated_function

def salvar_status_whatsapp(sessao, status):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET whatsapp_status = ?
        WHERE whatsapp_sessao = ?
    """, (status, sessao))

    conn.commit()
    conn.close()

@app.route('/uploads/imoveis/<filename>')
def foto_imovel(filename):
    return send_from_directory(
        '/data/uploads/imoveis',
        filename
    )



@app.route("/capturar_lead", methods=["POST"])
def capturar_lead():

    nome = request.form.get("nome")
    telefone = request.form.get("telefone")
    mensagem = request.form.get("mensagem")
    id_imovel = request.form.get("id_imovel")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO lead_site
        (
            nome,
            telefone,
            mensagem,
            id_imovel
        )
        VALUES (?, ?, ?, ?)
    """, (
        nome,
        telefone,
        mensagem,
        id_imovel
    ))

    conn.commit()
    conn.close()

    flash("Recebemos seu interesse. Em breve entraremos em contato!")

    return redirect(request.referrer)


@app.route("/excluir_cliente/<int:cliente_id>", methods=["POST"])
def excluir_cliente(cliente_id):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # apaga possíveis dados relacionados primeiro
    cursor.execute("""
        DELETE FROM clientes
        WHERE id = ?
    """,(cliente_id,))


    conn.commit()
    conn.close()


    return redirect("/clientes")

def criar_tabela_whatsapp():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS whatsapp_sessoes (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        empresa_id INTEGER,

        usuario_id INTEGER,

        session_name TEXT,

        status TEXT DEFAULT 'disconnected',

        telefone TEXT,

        qr_code TEXT,

        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,

        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """)

    conn.commit()
    conn.close()


criar_tabela_whatsapp()


@app.route("/leads_site")
@verificar_sessao
def leads_site():

    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            l.*,
            i.titulo
        FROM lead_site l
        INNER JOIN imoveis i
            ON i.id = l.id_imovel
        WHERE i.empresa_id = ?
        ORDER BY l.id DESC
    """, (empresa_id,))

    leads = cursor.fetchall()

    conn.close()

    return render_template(
        "leads_site.html",
        leads=leads
    )


@app.route("/enviar_imovel_link/<int:imovel_id>/<telefone>")
@verificar_sessao
def enviar_imovel_link(imovel_id, telefone):

    WPP_URL = "https://zoom-leggings-viability.ngrok-free.dev"


    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT *
        FROM imoveis
        WHERE id = ?
        """,
        (imovel_id,)
    )


    imovel = cursor.fetchone()

    conn.close()



    if not imovel:

        return jsonify({

            "sucesso":False,
            "erro":"Imóvel não encontrado"

        })



    link_imovel = (
        f"https://smartimob-production.up.railway.app/"
        f"informa-imovel/{imovel_id}"
    )



    mensagem = f"""
🏡 *OPORTUNIDADE DE IMÓVEL*

✨ *{imovel['titulo']}*

━━━━━━━━━━━━━━

📍 *Localização*
{imovel['rua'] or ''} 
{imovel['bairro']} - {imovel['cidade']}

💰 *Valor*
R$ {imovel['valor']}

🏠 *Detalhes do imóvel*

🛏 Quartos: {imovel['quartos']}
🚿 Banheiros: {imovel['banheiros']}
🚗 Vagas: {imovel['vaga_garagem']}
📐 Área: {imovel['area']} m²

{"🚽 Lavabo: Sim" if imovel['lavabo'] else ""}
{"🌴 Lazer: " + str(imovel['lazer']) if imovel['lazer'] else ""}
{"🌅 Sacada: Sim" if imovel['sacada'] else ""}

━━━━━━━━━━━━━━

💳 *Condições*

🏦 Financiamento:
{"Sim" if imovel['financiamento'] else "Não"}

📄 Condomínio:
R$ {imovel['condominio'] or 'Não informado'}

🏛 IPTU:
R$ {imovel['iptu'] or 'Não informado'}

━━━━━━━━━━━━━━

📝 *Descrição*

{imovel['descricao'] or 'Consulte detalhes'}

━━━━━━━━━━━━━━

Veja fotos, localização e mais informações:

🔗 {link_imovel}


💬 Gostou desse imóvel?
Posso te ajudar com mais informações 😊
"""


    telefone = (
        telefone
        .replace(" ","")
        .replace("-","")
        .replace("+","")
    )



    try:


        resp = requests.post(

            f"{WPP_URL}/enviar-imovel",

            json={

                "sessao":
                f"corretor_{session.get('usuario_id')}",


                "numero":
                telefone,


                "mensagem":
                mensagem

            },

            timeout=30

        )


        return jsonify(resp.json())



    except Exception as e:


        print("ERRO IMOVEL:", e)


        return jsonify({

            "sucesso":False,

            "erro":str(e)

        })


@app.route("/editar_cliente/<int:id>", methods=["GET"])
def pagina_editar(id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Busca o cliente específico pelo ID
    cursor.execute("SELECT * FROM clientes WHERE id = ?", (id,))
    cliente = cursor.fetchone()
    conn.close()
    
    # Retorna o template do formulário com os dados do cliente
    return render_template("perfil_cliente.html", cliente=cliente)




@app.route("/admin/gestao")
@verificar_sessao
@admin_required
def tela_gestao():
    empresa_id = session.get("empresa_id")
    conn = get_db()
    cursor = conn.cursor()

    # Totais
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE empresa_id = ?", (empresa_id,))
    total_usuarios = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM imoveis WHERE empresa_id = ?", (empresa_id,))
    total_imoveis = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM clientes WHERE empresa_id = ?", (empresa_id,))
    total_clientes = cursor.fetchone()[0]

    # Ranking com tratamento de dados
    cursor.execute("SELECT id, nome FROM usuarios WHERE empresa_id = ? AND nome IS NOT NULL", (empresa_id,))
    usuarios = cursor.fetchall()
    
    corretores = []
    for u in usuarios:
        u_id, u_nome = u
        cursor.execute("SELECT status_funil, COUNT(*) FROM clientes WHERE usuario_id = ? GROUP BY status_funil", (u_id,))
        contagem = dict(cursor.fetchall())
        
        corretores.append({
            'nome': u_nome,
            'total': sum(contagem.values()),
            'novo': contagem.get('Lead Novo', 0) + contagem.get('Novo Contato', 0),
            'negoc': contagem.get('Negociação', 0),
            'visita': contagem.get('Visita Agendada', 0),
            'venda': contagem.get('Concluido', 0),
            'desist': contagem.get('Desistencia', 0)
        })

    conn.close()
    return render_template("gestao.html", total_usuarios=total_usuarios, total_imoveis=total_imoveis, 
                           total_clientes=total_clientes, corretores=corretores)
# Decorator para o Super Admin
def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Apenas você (Super Admin) acessa
        if session.get('email') != 'seuemail@smartzen.com':
            return "Acesso Negado!", 403
        return f(*args, **kwargs)
    return decorated_function


@app.route("/simulador_financiamento")
def simulador_financiamento():
    return render_template("simulador_financiamento.html")

@app.route("/superadmin/dashboard")
@super_admin_required
def super_dashboard():
    # Lista todas as empresas e suas estatísticas
    empresas = db.execute("""
        SELECT e.id, e.nome_fantasia, 
        (SELECT COUNT(*) FROM usuarios WHERE empresa_id = e.id) as total_corretores,
        (SELECT COUNT(*) FROM imoveis WHERE empresa_id = e.id) as total_imoveis
        FROM empresas e
    """).fetchall()
    return render_template("super_admin.html", empresas=empresas)




@app.route("/fifit")
@verificar_sessao
def fifit():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ============================
    # FILTROS
    # ============================

    busca = request.args.get("busca", "").strip()
    tipo = request.args.get("tipo", "").strip()
    cidade = request.args.get("cidade", "").strip()
    bairro = request.args.get("bairro", "").strip()
    empreendimento = request.args.get("empreendimento", "").strip()
    quartos = request.args.get("quartos", "").strip()
    corretor = request.args.get("corretor", "").strip()
    status = request.args.get("status", "").strip()
    ordenar = request.args.get("ordenar", "recentes")

    sql = """
        SELECT
            i.*,
            u.nome AS corretor_nome,
            u.telefone AS corretor_telefone,
            u.foto_url AS corretor_foto
        FROM imoveis i
        LEFT JOIN usuarios u
            ON u.id = i.usuario_id
        WHERE i.compartilhar_fifit = 1
    """

    params = []

    # ============================
    # BUSCA
    # ============================

    if busca:
        sql += """
        AND (
            i.titulo LIKE ?
            OR i.descricao LIKE ?
            OR i.cidade LIKE ?
            OR i.bairro LIKE ?
            OR i.tipo LIKE ?
            OR i.empreendimento LIKE ?
            OR u.nome LIKE ?
        )
        """

        termo = f"%{busca}%"

        params.extend([
            termo,
            termo,
            termo,
            termo,
            termo,
            termo,
            termo
        ])

    # ============================
    # FILTROS
    # ============================

    if tipo:
        sql += " AND i.tipo = ?"
        params.append(tipo)

    if cidade:
        sql += " AND i.cidade = ?"
        params.append(cidade)

    if bairro:
        sql += " AND i.bairro = ?"
        params.append(bairro)

    if empreendimento:
        sql += " AND i.empreendimento = ?"
        params.append(empreendimento)

    if quartos:
        sql += " AND i.quartos >= ?"
        params.append(quartos)

    if corretor:
        sql += " AND u.nome = ?"
        params.append(corretor)

    if status:
        sql += " AND i.status = ?"
        params.append(status)

    # ============================
    # ORDENAÇÃO
    # ============================

    if ordenar == "menor_preco":
        sql += " ORDER BY i.valor ASC"

    elif ordenar == "maior_preco":
        sql += " ORDER BY i.valor DESC"

    elif ordenar == "maior_area":
        sql += " ORDER BY i.area DESC"

    elif ordenar == "mais_quartos":
        sql += " ORDER BY i.quartos DESC"

    else:
        sql += " ORDER BY i.id DESC"

    # ============================
    # CONSULTA PRINCIPAL
    # ============================

    cursor.execute(sql, params)

    imoveis = cursor.fetchall()

    imoveis_com_fotos = []

    for imovel in imoveis:

        cursor.execute("""
            SELECT nome_arquivo
            FROM fotos_imoveis
            WHERE imovel_id = ?
            ORDER BY id
        """, (imovel["id"],))

        fotos = [
            foto["nome_arquivo"]
            for foto in cursor.fetchall()
        ]

        imovel_dict = dict(imovel)
        imovel_dict["fotos"] = fotos

        imoveis_com_fotos.append(imovel_dict)

    # ============================
    # DADOS DOS FILTROS
    # ============================

    cursor.execute("""
        SELECT DISTINCT tipo
        FROM imoveis
        WHERE compartilhar_fifit = 1
        ORDER BY tipo
    """)
    tipos = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT cidade
        FROM imoveis
        WHERE compartilhar_fifit = 1
        ORDER BY cidade
    """)
    cidades = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT bairro
        FROM imoveis
        WHERE compartilhar_fifit = 1
        ORDER BY bairro
    """)
    bairros = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT empreendimento
        FROM imoveis
        WHERE compartilhar_fifit = 1
          AND empreendimento IS NOT NULL
          AND empreendimento <> ''
        ORDER BY empreendimento
    """)
    empreendimentos = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT status
        FROM imoveis
        WHERE compartilhar_fifit = 1
        ORDER BY status
    """)
    status_lista = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT u.nome
        FROM usuarios u
        INNER JOIN imoveis i
            ON i.usuario_id = u.id
        WHERE i.compartilhar_fifit = 1
        ORDER BY u.nome
    """)
    corretores = cursor.fetchall()

    conn.close()

    return render_template(
        "fifit.html",

        imoveis=imoveis_com_fotos,

        tipos=tipos,
        cidades=cidades,
        bairros=bairros,
        empreendimentos=empreendimentos,
        corretores=corretores,
        status_lista=status_lista,

        busca=busca,
        tipo=tipo,
        cidade=cidade,
        bairro=bairro,
        empreendimento=empreendimento,
        quartos=quartos,
        corretor=corretor,
        status=status,
        ordenar=ordenar
    )

NODE_API = "https://lucky-analysis-production-e497.up.railway.app"



@app.route("/catalogo")
def catalogo():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM imoveis ORDER BY id DESC")
    imoveis = cursor.fetchall()

    conn.close()

    return render_template("catalogo.html", imoveis=imoveis)





 
@app.route("/excluir_lead/<int:lead_id>", methods=["POST"])
@verificar_sessao
def excluir_lead(lead_id):

    empresa_id = session.get("empresa_id")


    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()


    # verifica se o lead pertence à empresa atual

    cursor.execute("""
        SELECT 
            l.id
        FROM lead_site l
        LEFT JOIN imoveis i
            ON i.id = l.id_imovel
        WHERE l.id = ?
        AND i.empresa_id = ?
    """, (lead_id, empresa_id))


    lead = cursor.fetchone()


    if not lead:

        conn.close()

        return jsonify({
            "sucesso": False,
            "erro": "Lead não encontrado"
        })



    cursor.execute("""
        DELETE FROM lead_site
        WHERE id = ?
    """, (lead_id,))


    conn.commit()
    conn.close()


    return jsonify({
        "sucesso": True
    })

 
@app.route("/atualizar_cliente/<int:id>", methods=["POST"])
def atualizar_cliente(id):
    nome = request.form.get("nome")
    telefone = request.form.get("telefone")
    email = request.form.get("email")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Atualiza o registro no banco
    cursor.execute("""
        UPDATE clientes 
        SET nome = ?, telefone = ?, email = ? 
        WHERE id = ?
    """, (nome, telefone, email, id))
    
    conn.commit()
    conn.close()
    
    return "Cliente atualizado com sucesso! <a href='/'>Voltar</a>"

@app.route("/importar_pdf")
@verificar_sessao
def importar_pdf():
    return render_template("importar_pdf.html")


@app.route('/analisar_cliente', methods=['POST'])
def analisar_cliente():

    import json
    import re

    dados = request.get_json()
    msg = dados.get('mensagem', '').strip()

    if not msg:
        return jsonify({
            "resultado": """
            <div class="card-msg-imovel">
                Digite o que o cliente procura.
            </div>
            """
        })

    empresa_id = session.get("empresa_id")

    if not empresa_id:
        return jsonify({
            "resultado": """
            <div class="card-msg-imovel">
                Usuário não autenticado.
            </div>
            """
        })

    # ==================================================
    # IA ANALISA PEDIDO
    # ==================================================

    try:

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": """
Você é um especialista imobiliário.

Extraia da mensagem:

bairro
cidade
valor_maximo
quartos
suites
vagas
tipo

Tipos permitidos:
apartamento
casa
sobrado
terreno
comercial

Retorne SOMENTE JSON válido.

Exemplo:

{
    "bairro":"Tatuapé",
    "cidade":"São Paulo",
    "valor_maximo":500000,
    "quartos":3,
    "suites":1,
    "vagas":2,
    "tipo":"apartamento"
}
"""
                },
                {
                    "role": "user",
                    "content": msg
                }
            ]
        )

        texto = (
            response.choices[0]
            .message.content
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        print("RESPOSTA IA:", texto)

        match = re.search(r'\{.*\}', texto, re.DOTALL)

        if match:
            filtros = json.loads(match.group())
        else:
            filtros = {}

    except Exception as erro:

        print("ERRO IA:", erro)

        return jsonify({
            "resultado": f"""
            <div class="card-msg-imovel">
                Erro ao analisar cliente.
            </div>
            """
        })

    # ==================================================
    # FILTROS
    # ==================================================

    bairro = filtros.get("bairro")
    cidade = filtros.get("cidade")
    tipo = filtros.get("tipo")

    quartos = int(filtros.get("quartos") or 0)
    suites = int(filtros.get("suites") or 0)
    vagas = int(filtros.get("vagas") or 0)

    valor_maximo = float(
        filtros.get("valor_maximo") or 999999999
    )

    # ==================================================
    # BUSCA IMÓVEIS
    # ==================================================

    conn = get_db()
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    query = """
    SELECT *
    FROM imoveis
    WHERE empresa_id = ?
    """

    parametros = [empresa_id]

    if bairro:
        query += " AND LOWER(bairro) LIKE ?"
        parametros.append(f"%{bairro.lower()}%")

    if cidade:
        query += " AND LOWER(cidade) LIKE ?"
        parametros.append(f"%{cidade.lower()}%")

    if tipo:
        query += " AND LOWER(tipo) = ?"
        parametros.append(tipo.lower())

    if quartos > 0:
        query += " AND quartos >= ?"
        parametros.append(quartos)

    if vagas > 0:
        query += " AND vaga_garagem >= ?"
        parametros.append(vagas)

    if valor_maximo < 999999999:
        query += " AND valor <= ?"
        parametros.append(valor_maximo)

    query += """
    ORDER BY valor ASC
    LIMIT 20
    """

    cursor.execute(query, parametros)

    imoveis = cursor.fetchall()

    conn.close()

    # ==================================================
    # SEM RESULTADO
    # ==================================================

    if not imoveis:

        return jsonify({
            "resultado": """
            <div class="card-msg-imovel">
                Nenhum imóvel encontrado com esses critérios.
            </div>
            """
        })

    # ==================================================
    # RESULTADO
    # ==================================================

    resultado = ""

    for imovel in imoveis:

        score = 50

        if bairro and imovel["bairro"]:
            if bairro.lower() in imovel["bairro"].lower():
                score += 15

        if cidade and imovel["cidade"]:
            if cidade.lower() in imovel["cidade"].lower():
                score += 10

        if tipo and imovel["tipo"]:
            if tipo.lower() == imovel["tipo"].lower():
                score += 10

        if quartos > 0:
            score += 5

        

        if vagas > 0:
            score += 5

        score = min(score, 100)

        valor_formatado = imovel["valor"] or "R$ 0,00"

        valor_str = str(imovel["valor"] or "0")

        valor_str = (
            valor_str
             .replace("R$", "")
             .replace("\xa0", "")
             .replace(".", "")
             .replace(",", ".")
             .strip()
        )
        try:
            valor = float(valor_str)
        except:
            valor = 0

        bairro_imovel = imovel["bairro"] if imovel["bairro"] else ""
        cidade_imovel = imovel["cidade"] if imovel["cidade"] else ""
        tipo_imovel = imovel["tipo"] if imovel["tipo"] else ""
        quartos_imovel = imovel["quartos"] if imovel["quartos"] else 0
        vagas_imovel = imovel["vaga_garagem"] if imovel["vaga_garagem"] else 0

        resultado += f"""
        <div class="card-msg-imovel">

            <div style="
                color:#facc15;
                font-weight:700;
                margin-bottom:8px;
            ">
                ⭐ Match IA: {score}%
            </div>

            <h3 style="
                color:#ffffff;
                margin-bottom:8px;
            ">
                {imovel['titulo']}
            </h3>

            <div style="
                color:#10b981;
                font-size:18px;
                font-weight:800;
            ">
                💰 {valor_formatado}
            </div>

            <div style="
                color:#cbd5e1;
                margin-top:10px;
                font-size:14px;
                line-height:1.6;
            ">
                📍 {bairro_imovel} - {cidade_imovel}<br>
                🏠 {tipo_imovel}<br>
                🛏 {quartos_imovel} quartos<br>
                🚗 {vagas_imovel} vagas
            </div>

            <a href="/imovel/{imovel['id']}"
               style="
                    display:inline-block;
                    margin-top:12px;
                    color:#10b981;
                    font-weight:700;
                    text-decoration:none;
               ">
                Ver imóvel →
            </a>

        </div>
        """

    return jsonify({
        "resultado": resultado
    })




@app.context_processor
def total_leads_site():

    try:

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM lead_site
        """)

        total = cursor.fetchone()[0]

        conn.close()

        return {
            "total_leads_site": total
        }

    except:
        return {
            "total_leads_site": 0
        }




@app.route('/data/uploads/imoveis/<filename>')
def servir_video_do_volume(filename):
    # Verifica se o arquivo realmente existe no seu volume /data/
    caminho_completo = os.path.join(app.config['UPLOAD_FOLDER_IMOVEIS'], filename)
    if os.path.exists(caminho_completo):
        return send_from_directory(app.config['UPLOAD_FOLDER_IMOVEIS'], filename)
    else:
        abort(404)




    
@app.route("/admin/usuario/senha/<int:id>", methods=["POST"])
@verificar_sessao
@admin_required
def alterar_senha_usuario(id):

    nova_senha = request.form.get("senha")

    senha_hash = generate_password_hash(nova_senha)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET senha=?
        WHERE id=?
        AND empresa_id=?
    """, (
        senha_hash,
        id,
        session.get("empresa_id")
    ))

    conn.commit()
    conn.close()

    return redirect("/admin/usuarios")


@app.route("/analisar_pdf", methods=["POST"])
@verificar_sessao
def analisar_pdf():
    arquivo = request.files.get("pdf")

    if not arquivo:
        return "PDF não enviado", 400

    # Configuração de diretório
    pasta = "data/uploads/pdf"
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, arquivo.filename)

    # Salva o arquivo temporariamente
    arquivo.save(caminho)

    texto = ""
    print("COMEÇOU EXTRAÇÃO PDF")
    
    try:
        with pdfplumber.open(caminho, laparams={"detect_vertical": False}) as pdf:
            for pagina in pdf.pages:
                conteudo = pagina.extract_text()
                if conteudo:
                    texto += conteudo + "\n"
        
        # Processa a extração
        imoveis = extrair_imoveis(texto)
        print(f"Foram encontrados {len(imoveis)} imóveis.")
        links = extrair_links_pdf(caminho)

        print("LINKS ENCONTRADOS:")
        print(links)

    finally:
        # Garante que o arquivo será deletado mesmo que ocorra um erro
        if os.path.exists(caminho):
            os.remove(caminho)

    return render_template(
        "preview_importacao.html",
        imoveis=imoveis,
        links=links
    )

@app.route("/admin/ativar-usuario", methods=["POST"])
@verificar_sessao
def ativar_usuario():

    user_id = request.form["user_id"]

    conn = sqlite3.connect(DB_PATH)

    conn.execute(
        "UPDATE usuarios SET ativo = 1 WHERE id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()

    flash("Usuário ativado com sucesso.")

    return redirect("/admin/novo-usuario")


@app.route("/admin/desativar-usuario", methods=["POST"])
@verificar_sessao
def desativar_usuario():

    user_id = request.form["user_id"]

    conn = sqlite3.connect(DB_PATH)

    conn.execute(
        "UPDATE usuarios SET ativo = 0 WHERE id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()

    flash("Usuário desativado com sucesso.")

    return redirect("/admin/novo-usuario")

@app.route("/clientes")
@verificar_sessao
def listar_clientes():

    empresa_id = session.get("empresa_id")

    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if data_inicio and data_fim:

        cursor.execute("""
            SELECT *
            FROM clientes
            WHERE empresa_id = ?
            AND data_criacao BETWEEN ? AND ?
            ORDER BY id DESC
        """, (
            empresa_id,
            data_inicio,
            data_fim
        ))

    else:

        cursor.execute("""
            SELECT *
            FROM clientes
            WHERE empresa_id = ?
            ORDER BY id DESC
        """, (empresa_id,))

    clientes = cursor.fetchall()

    conn.close()

    return render_template(
        "clientes.html",
        clientes=clientes,
        data_inicio=data_inicio,
        data_fim=data_fim
    )
 



@app.route("/superadmin/usuario/editar/<int:user_id>", methods=["POST"])
@super_admin_required
def editar_usuario(user_id):
    dados = request.json
    # Exemplo: Desativar login ou alterar senha
    if 'nova_senha' in dados:
        db.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (gerar_hash(dados['nova_senha']), user_id))
    if 'ativo' in dados:
        db.execute("UPDATE usuarios SET status = ? WHERE id = ?", (dados['ativo'], user_id))
    db.commit()
    return jsonify({"status": "sucesso"})


@app.route("/ceo/usuarios")
@verificar_sessao
@somente_ceo
def ceo_usuarios():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM usuarios
        ORDER BY nome
    """)

    usuarios = cursor.fetchall()

    conn.close()

    return render_template(
        "ceo/usuarios.html",
        usuarios=usuarios
    )

@app.route("/admin/usuarios")
@verificar_sessao
@admin_required
def admin_usuarios():

    empresa_id = session.get("empresa_id")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id,nome,email,is_admin,status
        FROM usuarios
        WHERE empresa_id=?
    """, (empresa_id,))

    usuarios = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_usuarios.html",
        usuarios=usuarios
    )



@app.route("/importar_clientes", methods=["GET", "POST"])
@verificar_sessao
def importar_clientes():

    if request.method == "POST":

        import pandas as pd
        import sqlite3

        arquivo = request.files["arquivo"]

        if not arquivo:
            flash("Selecione um arquivo.")
            return redirect("/importar_clientes")

        nome_arquivo = arquivo.filename.lower()

        try:

            if nome_arquivo.endswith(".xlsx"):
                df = pd.read_excel(arquivo, engine="openpyxl")

            elif nome_arquivo.endswith(".csv"):
                df = pd.read_csv(arquivo)

            else:
                flash("Envie um arquivo XLSX ou CSV.")
                return redirect("/importar_clientes")

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            adicionados = 0
            duplicados = 0

            for _, row in df.iterrows():

                nome = str(row.get("nome", "")).strip()

                telefone = str(row.get("telefone", "")).strip()

                interesse = str(row.get("interesse", "")).strip()

                faixa_preco = str(row.get("faixa_preco", "")).strip()

                if not telefone:
                    continue

                telefone = (
                    telefone
                    .replace(".0", "")
                    .replace(" ", "")
                    .replace("-", "")
                    .replace("(", "")
                    .replace(")", "")
                )

                cursor.execute("""
                    SELECT id
                    FROM clientes
                    WHERE telefone = ?
                    AND empresa_id = ?
                """, (
                    telefone,
                    session["empresa_id"]
                ))

                if cursor.fetchone():
                    duplicados += 1
                    continue

                cursor.execute("""
                    INSERT INTO clientes
                    (
                        nome,
                        telefone,
                        email,
                        interesse,
                        faixa_preco,
                        bairro,
                        sobre,
                        entrada,
                        pagamento,
                        usuario_id,
                        empresa_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    nome,
                    telefone,
                    "",
                    interesse,
                    faixa_preco,
                    "",
                    "",
                    "",
                    "",
                    session["usuario_id"],
                    session["empresa_id"]
                ))

                adicionados += 1

            conn.commit()
            conn.close()

            flash(
                f"{adicionados} clientes importados | {duplicados} duplicados ignorados"
            )

            return redirect("/clientes")

        except Exception as e:

            flash(f"Erro ao importar: {str(e)}")
            return redirect("/importar_clientes")

    return render_template("importar_clientes.html")

@app.route("/superadmin/empresa/<int:empresa_id>/usuarios")
@super_admin_required
def gerenciar_usuarios_empresa(empresa_id):
    # Busca todos os usuários da empresa selecionada
    usuarios = db.execute("""
        SELECT id, nome, email, cargo, is_admin 
        FROM usuarios WHERE empresa_id = ?
    """, (empresa_id,)).fetchall()

    return render_template("gerenciar_usuarios.html", usuarios=usuarios, empresa_id=empresa_id)

@app.route("/privacidade")
def privacidade():
    return render_template("privacidade.html")

@app.route("/superadmin/usuario/promover/<int:usuario_id>", methods=["POST"])
@super_admin_required
def tornar_admin(usuario_id):
    db.execute("UPDATE usuarios SET is_admin = 1 WHERE id = ?", (usuario_id,))
    db.commit()
    return jsonify({"status": "sucesso", "mensagem": "Usuário agora é Administrador!"})    


# --- FUNÇÃO DE LOGIN ---
def verificar_login():
    if "usuario_id" not in session: return "redirect_login"
    if session.get("is_admin") == 1: return "ativo"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status_assinatura, validade_assinatura FROM usuarios WHERE id = ?", (session["usuario_id"],))
    user = cursor.fetchone()
    conn.close()

    if not user: return "redirect_login"
    if user[0] == "bloqueado": return "bloqueado"
    if user[1]:
        if datetime.now() > datetime.strptime(user[1], "%Y-%m-%d"): return "vencido"
    return "ativo"

# --- ROTA CONFIGURAÇÕES (CORRIGIDA) ---

    # Busca os dados atuais garantindo o escopo da empresa
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nome, foto_url FROM usuarios 
        WHERE id = ? AND empresa_id = ?
    """, (session["usuario_id"], session["empresa_id"]))
    usuario = cursor.fetchone()
    conn.close()

    return render_template("configuracoes.html", usuario=usuario)

# --- ROTA CADASTRAR IMOVEL (CORRIGIDA) ---
import os
from flask import jsonify, request

@app.route("/renderizar-video", methods=["POST"])
@verificar_sessao
def renderizar_video():
    dados = request.json
    imovel_id = dados.get('imovel_id')

    pasta_fotos = app.config['UPLOAD_FOLDER_IMOVEIS']
    arquivos = [f for f in os.listdir(pasta_fotos) if f.startswith(f"{imovel_id}_")]

    if not arquivos:
        return jsonify({"status": "erro", "mensagem": "Nenhuma foto encontrada."})

    arquivos.sort()

    # 1. Cria os clips das fotos
    clips = []
    for nome_arquivo in arquivos:
        caminho_foto = os.path.join(pasta_fotos, nome_arquivo)
        clip = ImageClip(caminho_foto).resized(height=720).with_duration(3)
        clips.append(clip)

    # 2. Junta os clips
    video = concatenate_videoclips(clips, method="compose")

    # 3. Adiciona o áudio (Processamento único)
    caminho_audio = os.path.join('static', 'assets', 'musicas', 'fundo_imobiliaria.mp3')
    if os.path.exists(caminho_audio):
        audio_clip = AudioFileClip(caminho_audio).with_duration(video.duration)
        audio_clip = audio_clip.audio_fadein(1).audio_fadeout(1)
        video = video.with_audio(audio_clip)

    # 4. Renderiza o vídeo final uma única vez
    nome_video = f"video_imovel_{imovel_id}.mp4"
    caminho_video = os.path.join(app.config['UPLOAD_FOLDER_IMOVEIS'], nome_video)

    video.write_videofile(caminho_video, codec="libx264", audio_codec="aac", fps=24)

    # 5. Limpa a memória fechando o vídeo
    video.close()

    return jsonify({
        "status": "sucesso", 
        # A URL deve começar com /data/uploads... para bater com a rota que criamos
        "url_video": f"/data/uploads/imoveis/{nome_video}"
        })


@app.route("/ceo")
@verificar_sessao
@somente_ceo
def dashboard_ceo():

    return render_template("ceo/dashboard_ceo.html")
     
@app.route('/site/<subdominio>')
def exibir_site(subdominio):

    conn = sqlite3.connect('/data/imobiliaria.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    empresa = cursor.execute(
        """
        SELECT *
        FROM configuracoes_site
        WHERE subdominio = ?
        """,
        (subdominio,)
    ).fetchone()

    if not empresa:
        conn.close()
        return "Site não encontrado", 404

    rows = cursor.execute(
        """
        SELECT *
        FROM imoveis
        WHERE empresa_id = ?
        ORDER BY id DESC
        """,
        (empresa['empresa_id'],)
    ).fetchall()

    imoveis = []

    for row in rows:

        imovel = dict(row)

        fotos = cursor.execute(
            """
            SELECT nome_arquivo
            FROM fotos_imoveis
            WHERE imovel_id = ?
            ORDER BY id ASC
            """,
            (imovel["id"],)
        ).fetchall()

        imovel["fotos"] = [
            foto["nome_arquivo"]
            for foto in fotos
        ]

        imoveis.append(imovel)

    conn.close()

    return render_template(
        "template_site.html",
        empresa=empresa,
        imoveis=imoveis
    )




@app.route("/excluir-foto/<int:foto_id>")
@verificar_sessao
def excluir_foto(foto_id):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Busca a foto
    cursor.execute("""
        SELECT *
        FROM fotos_imoveis
        WHERE id = ?
    """, (foto_id,))

    foto = cursor.fetchone()

    if not foto:
        conn.close()
        return redirect(request.referrer)

    # Caminho do arquivo
    caminho_foto = os.path.join(
        app.config['UPLOAD_FOLDER_IMOVEIS'],
        foto["nome_arquivo"]
    )

    # Remove arquivo físico
    if os.path.exists(caminho_foto):
        os.remove(caminho_foto)

    # Remove do banco
    cursor.execute("""
        DELETE FROM fotos_imoveis
        WHERE id = ?
    """, (foto_id,))

    conn.commit()
    conn.close()

    return redirect(request.referrer)


@app.route("/campanhas")
@verificar_sessao
def campanhas():

    empresa_id = session.get('empresa_id')


    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()


    cursor.execute("""
        SELECT *
        FROM clientes
        WHERE empresa_id = ?
        ORDER BY id DESC
    """, (empresa_id,))


    clientes = cursor.fetchall()


    conn.close()


    user_id = session.get("user_id", None)

    return render_template(
        "campanhas.html",
        user_id=user_id,
        clientes=clientes
    )
     

@app.route("/teste_envio", methods=["POST"])
def teste_envio():

    try:
        data = request.get_json() or {}

        print("🔥 TESTE RECEBIDO:", data)

        telefone = data.get("telefone")
        mensagem = data.get("mensagem")

        if not telefone or not mensagem:
            return jsonify({
                "status": "error",
                "erro": "telefone e mensagem obrigatórios"
            }), 400

        WPP_URL = "https://zoom-leggings-viability.ngrok-free.dev"

        resp = requests.post(
            f"{WPP_URL}/enviar",
            json={
                "sessao": "empresa_1",
                "numero": telefone,
                "mensagem": mensagem
            },
            timeout=20
        )

        print("📤 RESPOSTA NODE:", resp.text)

        return jsonify(resp.json())

    except Exception as e:
        print("🔥 ERRO TESTE:", str(e))
        return jsonify({"status": "error", "erro": str(e)})
     
@app.route('/termos')
def termos():
    return render_template('termos.html')





WPP_URL = "https://zoom-leggings-viability.ngrok-free.dev"
TOKEN = "THISISMYSECURETOKEN"


@app.route("/whatsapp/enviar", methods=["POST"])
def whatsapp_enviar():

    try:

        data = request.json


        session = data.get("session")
        numero = data.get("numero")
        mensagem = data.get("mensagem")


        print("==============================")
        print("📤 ENVIO WHATSAPP")
        print("Sessão:", session)
        print("Número recebido:", numero)
        print("Mensagem:", mensagem)
        print("==============================")


        if not session:

            return jsonify({

                "success": False,
                "erro": "Sessão não informada"

            })


        if not numero or not mensagem:

            return jsonify({

                "success": False,
                "erro": "Número ou mensagem vazio"

            })



        # ==========================
        # LIMPAR TELEFONE
        # ==========================


        numero = (
            numero
            .replace("@c.us", "")
            .replace("@lid", "")
            .replace("+", "")
            .replace(" ", "")
            .replace("-", "")
            .strip()
        )


        if not numero.startswith("55"):

            numero = "55" + numero



        print("Número corrigido:", numero)



        # ==========================
        # CHECK NUMBER STATUS
        # ==========================


        check_url = (
            f"{WPP_URL}/api/"
            f"{session}/check-number-status/"
            f"{numero}"
        )


        check = requests.get(

            check_url,

            headers={

                "Authorization":
                f"Bearer {TOKEN}"

            },

            timeout=30

        )



        print("==============================")
        print("CHECK NUMBER:")
        print(check.text)
        print("==============================")



        try:

            dados_check = check.json()

        except:

            dados_check = {}



        # ==========================
        # VALIDAR NÚMERO
        # ==========================


        if (
            dados_check.get("status") == 404
            or
            dados_check.get("numberExists") == False
        ):

            return jsonify({

                "success":False,

                "erro":
                "Número não possui WhatsApp",

                "check":
                dados_check

            })



        # ==========================
        # PEGAR ID CORRETO
        # ==========================


        phone_id = None



        if dados_check.get("id"):


            if isinstance(
                dados_check["id"],
                dict
            ):


                phone_id = (
                    dados_check["id"]
                    .get("_serialized")
                )


            else:

                phone_id = dados_check["id"]




        # fallback

        if not phone_id:

            phone_id = numero + "@c.us"



        print("==============================")
        print("ID FINAL ENVIO:")
        print(phone_id)
        print("==============================")





        # ==========================
        # ENVIAR MENSAGEM
        # ==========================


        send_url = (
            f"{WPP_URL}/api/"
            f"{session}/send-message"
        )



        resposta = requests.post(

            send_url,

            headers={

                "Authorization":
                f"Bearer {TOKEN}",

                "Content-Type":
                "application/json"

            },


            json={

                "phone": phone_id,

                "message": mensagem

            },


            timeout=30

        )



        print("==============================")
        print("RETORNO WPPCONNECT:")
        print(resposta.text)
        print("==============================")





        try:

            retorno = resposta.json()


        except:


            retorno = {

                "raw":
                resposta.text

            }



        return jsonify(retorno)



    except Exception as e:


        print("==============================")
        print("❌ ERRO ENVIO WHATSAPP")
        print(e)
        print("==============================")


        return jsonify({

            "success":False,

            "erro":str(e)

        })
     
@app.route("/enviar_imovel_match", methods=["POST"])
@verificar_sessao
def enviar_imovel_match():

    try:

        data = request.get_json()

        cliente_id = data.get("cliente_id")
        imovel_id = data.get("imovel_id")

        empresa_id = session["empresa_id"]
        usuario_id = session["usuario_id"]

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()

        # CLIENTE

        cursor.execute("""
            SELECT *
            FROM clientes
            WHERE id = ?
            AND empresa_id = ?
        """, (cliente_id, empresa_id))

        cliente = cursor.fetchone()

        if not cliente:

            conn.close()

            return jsonify({
                "status":"error",
                "erro":"Cliente não encontrado"
            })

        # IMÓVEL

        cursor.execute("""
            SELECT *
            FROM imoveis
            WHERE id = ?
            AND empresa_id = ?
        """, (imovel_id, empresa_id))

        imovel = cursor.fetchone()

        if not imovel:

            conn.close()

            return jsonify({
                "status":"error",
                "erro":"Imóvel não encontrado"
            })

        # SESSÃO WPP

        cursor.execute("""
            SELECT whatsapp_sessao
            FROM usuarios
            WHERE id = ?
        """, (usuario_id,))

        usuario = cursor.fetchone()

        conn.close()

        # TELEFONE

        telefone = str(cliente["telefone"])

        telefone = ''.join(
            filter(str.isdigit, telefone)
        )

        if not telefone.startswith("55"):
            telefone = "55" + telefone

        # MENSAGEM

        mensagem = f"""
🏠 *{imovel['titulo']}*

💰 Valor: {imovel['valor']}

📍 {imovel['bairro']} - {imovel['cidade']}

🚗 Vagas > {imovel['vaga_garagem']} - 🛏️ Quartos > {imovel['quartos']}

Olá {cliente['nome']}!

Encontrei um imóvel que combina com seu perfil.

Quer ver mais detalhes e fotos > { imovel['link']}?
Estou aqui para esclarecer duvidas !
"""

        WPP_URL = "https://zoom-leggings-viability.ngrok-free.dev"

        resp = requests.post(

            f"{WPP_URL}/enviar",

            json={

                "sessao":
                    usuario["whatsapp_sessao"],

                "numero":
                    telefone,

                "mensagem":
                    mensagem

            },

            timeout=120

        )

        return jsonify(
            resp.json()
        )

    except Exception as e:

        print("ERRO MATCH:", e)

        return jsonify({

            "status":"error",

            "erro":str(e)

        })


@app.route("/cadastrar_imovel", methods=["GET", "POST"])
@verificar_sessao
def cadastrar_imovel():
    if request.method == "POST":

        empresa_id = session.get("empresa_id")
        user_id = session.get("usuario_id")
        data_criacao = datetime.now().strftime("%Y-%m-%d")

        valor = request.form.get("valor", "")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO imoveis (
                titulo, tipo, valor, cidade, bairro,
                quartos, banheiros, area, status, descricao,
                rua, iptu, condominio, link, cep,
                vaga_garagem, lazer, sacada, lavabo, prazo, parcela, anuais, entrada, banheiros21, proprietario1, telefone2, mobilia,
                usuario_id, empresa_id, data_criacao
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("titulo"),
            request.form.get("tipo"),
            valor,
            request.form.get("cidade"),
            request.form.get("bairro"),
            request.form.get("quartos"),
            request.form.get("banheiros"),
            request.form.get("area"),
            request.form.get("status"),
            request.form.get("descricao"),
            request.form.get("rua"),
            request.form.get("iptu"),
            request.form.get("condominio"),
            request.form.get("link"),
            request.form.get("cep"),
            request.form.get("vaga_garagem"),
            request.form.get("lazer"),
            request.form.get("sacada"),
            request.form.get("lavabo"),
            request.form.get("prazo"),
            request.form.get("parcela"),
            request.form.get("anuais"),
            request.form.get("entrada"),
            request.form.get("banheiros21"),
            request.form.get("proprietario1"),
            request.form.get("telefone2"),
            request.form.get("mobilia"),

            user_id,
            empresa_id,
            data_criacao
        ))

        imovel_id = cursor.lastrowid

        arquivos = request.files.getlist("fotos[]")

        for file in arquivos:
            if file and file.filename != "":
                nome_seguro = secure_filename(file.filename)
                nome_foto = f"{imovel_id}_{int(datetime.now().timestamp())}_{nome_seguro}"

                caminho_salvamento = os.path.join(
                    app.config['UPLOAD_FOLDER_IMOVEIS'],
                    nome_foto
                )

                file.save(caminho_salvamento)

                cursor.execute("""
                    INSERT INTO fotos_imoveis (imovel_id, nome_arquivo)
                    VALUES (?, ?)
                """, (imovel_id, nome_foto))

        conn.commit()
        conn.close()

        return redirect("/imoveis")

    return render_template("cadastrar_imovel.html")
# (Mantenha o restante das suas outras rotas abaixo aqui...)


api_key=os.getenv('GCP_API_KEY')

# ==========================================
# FUNÇÃO AUXILIAR: VERIFICAÇÃO DE ASSINATURA
# ==========================================
def verificar_login():
    """Retorna o status do usuário ou redirecionamento se não logado."""
    if "usuario_id" not in session:
        return "redirect_login"

    # Se for o Administrador Master, ele está sempre liberado
    if session.get("is_admin") == 1:
        return "ativo"

    # Consulta o status direto no banco de dados para segurança máxima
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status_assinatura, validade_assinatura FROM usuarios WHERE id = ?",
        (session["usuario_id"],),
    )
    user = cursor.fetchone()
    conn.close()

    if not user:
        return "redirect_login"

    status, validade = user[0], user[1]

    # 1. Se estiver bloqueado manualmente pelo Admin
    if status == "bloqueado":
        return "bloqueado"

    # 2. Se a data de validade expirou
    if validade:
        data_vencimento = datetime.strptime(validade, "%Y-%m-%d")
        if datetime.now() > data_vencimento:
            return "vencido"

    return "ativo"


@app.route("/api/session/create", methods=["POST"])
def create_session():
    data = request.json
    session = data.get("session")

    # chama WPPConnect
    url = f"{WPP_URL}/api/{session}/start-session"

    res = requests.post(url, headers={
        "Authorization": f"Bearer {TOKEN}"
    }, json={"waitQrCode": True})

    return jsonify(res.json())

@app.route("/api/session/<session>/status")
def session_status(session):

    url = f"{WPP_URL}/api/{session}/start-session"

    res = requests.post(url, headers={
        "Authorization": f"Bearer {TOKEN}"
    }, json={})

    return jsonify(res.json())

logs = {}

@app.route("/api/session/<session>/logs")
def get_logs(session):
    return jsonify(logs.get(session, []))

@app.route("/api/session/<session>/qr")
def get_qr(session):

    url = f"{WPP_URL}/api/{session}/start-session"

    res = requests.post(url, headers={
        "Authorization": f"Bearer {TOKEN}"
    }, json={"waitQrCode": True})

    data = res.json()

    return jsonify({
        "qrcode": data.get("qrcode"),
        "status": data.get("status")
    })

@app.route("/atualizar_senha", methods=["POST"])
def atualizar_senha():
    senha_atual = request.form.get("senha_atual")
    nova_senha = request.form.get("nova_senha")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT senha FROM usuarios WHERE id = ?", (session["usuario_id"],))
    hash_atual = cursor.fetchone()[0]

    if check_password_hash(hash_atual, senha_atual):
        novo_hash = generate_password_hash(nova_senha)
        cursor.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (novo_hash, session["usuario_id"]))
        conn.commit()
        flash("Senha atualizada com sucesso!", "success") # <--- A MENSAGEM
    else:
        flash("Senha atual incorreta.", "danger") # <--- ERRO# Aqui você pode adicionar um flash("Senha atualizada!")

    conn.close()
    return redirect("/configuracoes")


@app.route("/sistema")
@verificar_sessao
def index():

    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()


    cursor.execute(
        "SELECT COUNT(*) FROM clientes WHERE empresa_id=?",
        (empresa_id,)
    )

    total_clientes = cursor.fetchone()[0]


    cursor.execute(
        "SELECT COUNT(*) FROM imoveis WHERE empresa_id=?",
        (empresa_id,)
    )

    total_imoveis = cursor.fetchone()[0]


    cursor.execute("""
        SELECT *
        FROM configuracoes_site
        WHERE empresa_id=?
    """,(empresa_id,))


    site = cursor.fetchone()


    conn.close()


    return render_template(
        "index.html",
        total_clientes=total_clientes,
        total_imoveis=total_imoveis,
        site=site
    )

@app.route("/")
def landing():

    return render_template("landing.html")
# ==========================================
# 2. SISTEMA DE LOGIN, USUÁRIOS E LOGOUT
# ==========================================
@app.route("/match_ia")
@verificar_sessao
def match_ia():
    # Bloqueio extra para admin não entrar aqui


    empresa_id = session.get("empresa_id")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ISOLAMENTO: Puxa apenas dados vinculados à empresa do usuário logado
    cursor.execute("""
        SELECT id, nome, interesse, faixa_preco, bairro, telefone 
        FROM clientes WHERE empresa_id = ?
    """, (empresa_id,))
    clientes = cursor.fetchall()

    cursor.execute("""
SELECT
    i.id,
    i.titulo,
    i.tipo,
    i.valor,
    i.cidade,
    i.bairro,
    (
        SELECT nome_arquivo
        FROM fotos_imoveis f
        WHERE f.imovel_id = i.id
        LIMIT 1
    ) as foto
FROM imoveis i
WHERE i.empresa_id = ?
""", (empresa_id,))
    imoveis = cursor.fetchall()
    conn.close()

    matches = []
    # ... (lógica de match permanece a mesma, agora operando em um ambiente isolado)
    for c in clientes:
        c_id, c_nome, c_interesse, c_faixa, c_bairro, c_telefone = c
        c_bairro_txt = str(c_bairro).lower().strip() if c_bairro else ""
        interesse_txt = str(c_interesse).lower().strip() if c_interesse else ""

        for i in imoveis:
            i_id, i_titulo, i_tipo, i_valor, i_cidade, i_bairro, i_foto = i
            i_bairro_txt = str(i_bairro).lower().strip() if i_bairro else ""

            porcentagem = 0
            if i_bairro_txt and (i_bairro_txt == c_bairro_txt or i_bairro_txt in interesse_txt):
                porcentagem += 50

            try:
                imovel_num = float(''.join(filter(str.isdigit, str(i_valor))))
                cliente_num = float(''.join(filter(str.isdigit, str(c_faixa))))
                if imovel_num <= (cliente_num * 1.10):
                    porcentagem += 50
            except:
                if c_faixa and str(i_valor).strip() in str(c_faixa).strip():
                    porcentagem += 50

            if porcentagem >= 50:
                matches.append({
                    "cliente_nome": c_nome,
                    "cliente_telefone": c_telefone,
                    "imovel_id": i_id,
                    "imovel_titulo": i_titulo,
                    "imovel_foto": i_foto,
                    "imovel_valor": i_valor,
                    "imovel_local": f"{i_bairro}, {i_cidade}" if i_bairro else i_cidade,
                    "porcentagem": porcentagem
                })

    matches = sorted(matches, key=lambda x: x["porcentagem"], reverse=True)
    return render_template("match_ia.html", matches=matches)


@app.route("/site/<slug>")
def site_publico(slug):

    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Busca configuração do site
    cursor.execute("""
        SELECT *
        FROM configuracoes_site
        WHERE subdominio = ?
    """, (slug,))

    empresa = cursor.fetchone()

    if not empresa:
        conn.close()
        return "Site não encontrado"

    # Busca imóveis da empresa
    cursor.execute("""
        SELECT *
        FROM imoveis
        WHERE empresa_id = ?
        ORDER BY id DESC
    """, (empresa["empresa_id"],))

    rows = cursor.fetchall()

    imoveis = []

    for row in rows:

        imovel = dict(row)

        # Busca todas as fotos
        cursor.execute("""
            SELECT nome_arquivo
            FROM fotos_imoveis
            WHERE imovel_id = ?
            ORDER BY id ASC
        """, (imovel["id"],))

        fotos = cursor.fetchall()

        imovel["fotos"] = []

        for foto in fotos:

            url_foto = (
                "/data/uploads/imoveis/"
                + foto["nome_arquivo"]
            )

            imovel["fotos"].append(url_foto)

        # Foto capa
        if imovel["fotos"]:
            imovel["foto_capa"] = imovel["fotos"][0]
        else:
            imovel["foto_capa"] = None

        print(
            f"IMÓVEL {imovel['id']} -> "
            f"{len(imovel['fotos'])} fotos"
        )

        imoveis.append(imovel)

    conn.close()

    return render_template(
        "site_publico.html",
        empresa=empresa,
        imoveis=imoveis
   )

@app.route("/uploads/logos/<path:arquivo>")
def logo_empresa(arquivo):
    return send_from_directory(
        "/data/uploads/logos",
        arquivo
    )
from collections import defaultdict

@app.route("/dashboard_v2")
@verificar_sessao
def dashboard_v2():

    empresa_id = session.get("empresa_id")
    hoje = datetime.now()

    mes_atual = hoje.strftime("%m")
    ano_atual = hoje.strftime("%Y")

    if hoje.month == 1:
        mes_anterior = "12"
        ano_anterior = str(hoje.year - 1)
    else:
        mes_anterior = f"{hoje.month-1:02}"
        ano_anterior = str(hoje.year)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # =====================================================
    # FUNÇÃO AUXILIAR
    # =====================================================

    def calcular_percentual(atual, anterior):
        if anterior == 0:
            return 100 if atual > 0 else 0
        return round(((atual - anterior) / anterior) * 100)

    # =====================================================
    # TOTAIS
    # =====================================================

    cursor.execute(
        "SELECT COUNT(*) FROM clientes WHERE empresa_id=?",
        (empresa_id,)
    )
    total_clientes = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM imoveis WHERE empresa_id=?",
        (empresa_id,)
    )
    total_imoveis = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM lead_site l
        INNER JOIN imoveis i
            ON i.id = l.id_imovel
        WHERE i.empresa_id = ?
    """, (empresa_id,))
    total_leads = cursor.fetchone()[0]

    # =====================================================
    # CLIENTES MÊS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM clientes
        WHERE empresa_id=?
        AND strftime('%m',data_criacao)=?
        AND strftime('%Y',data_criacao)=?
    """, (empresa_id, mes_atual, ano_atual))

    clientes_mes = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM clientes
        WHERE empresa_id=?
        AND strftime('%m',data_criacao)=?
        AND strftime('%Y',data_criacao)=?
    """, (empresa_id, mes_anterior, ano_anterior))

    clientes_mes_anterior = cursor.fetchone()[0]

    pct_clientes = calcular_percentual(
        clientes_mes,
        clientes_mes_anterior
    )

    # =====================================================
    # IMÓVEIS MÊS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM imoveis
        WHERE empresa_id=?
        AND strftime('%m',data_criacao)=?
        AND strftime('%Y',data_criacao)=?
    """, (empresa_id, mes_atual, ano_atual))

    imoveis_mes = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM imoveis
        WHERE empresa_id=?
        AND strftime('%m',data_criacao)=?
        AND strftime('%Y',data_criacao)=?
    """, (empresa_id, mes_anterior, ano_anterior))

    imoveis_mes_anterior = cursor.fetchone()[0]

    pct_imoveis = calcular_percentual(
        imoveis_mes,
        imoveis_mes_anterior
    )

    # =====================================================
    # LEADS MÊS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM lead_site l
        INNER JOIN imoveis i
            ON i.id=l.id_imovel
        WHERE i.empresa_id=?
        AND strftime('%m',l.data_criacao)=?
        AND strftime('%Y',l.data_criacao)=?
    """, (empresa_id, mes_atual, ano_atual))

    leads_mes = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM lead_site l
        INNER JOIN imoveis i
            ON i.id=l.id_imovel
        WHERE i.empresa_id=?
        AND strftime('%m',l.data_criacao)=?
        AND strftime('%Y',l.data_criacao)=?
    """, (empresa_id, mes_anterior, ano_anterior))

    leads_mes_anterior = cursor.fetchone()[0]

    pct_leads = calcular_percentual(
        leads_mes,
        leads_mes_anterior
    )

    # =====================================================
    # MATCH IA
    # Clientes com interesse preenchido
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM clientes
        WHERE empresa_id=?
        AND interesse IS NOT NULL
        AND interesse <> ''
    """, (empresa_id,))

    total_matchs = cursor.fetchone()[0]

    # =====================================================
    # BARRAS
    # =====================================================

    progresso_clientes = min(total_clientes, 100)
    progresso_imoveis = min(total_imoveis, 100)
    progresso_leads = min(total_leads, 100)
    progresso_match = min(total_matchs, 100)

    # =====================================================
    # CONFIGURAÇÕES
    # =====================================================

    cursor.execute(
        "SELECT * FROM configuracoes_site WHERE empresa_id=?",
        (empresa_id,)
    )

    site = cursor.fetchone()

    # =====================================================
    # CLIENTES POR MÊS
    # =====================================================

    cursor.execute("""
        SELECT
            strftime('%m',data_criacao) AS mes,
            COUNT(*) AS total
        FROM clientes
        WHERE empresa_id=?
        GROUP BY mes
        ORDER BY mes
    """, (empresa_id,))

    meses_clientes = {
        f"{i:02}":0
        for i in range(1,13)
    }

    for row in cursor.fetchall():
        meses_clientes[row["mes"]] = row["total"]

    labels_clientes = [
        "Jan","Fev","Mar","Abr","Mai","Jun",
        "Jul","Ago","Set","Out","Nov","Dez"
    ]

    dados_clientes = list(meses_clientes.values())

        # =====================================================
    # IMÓVEIS POR TIPO
    # =====================================================

    cursor.execute("""
        SELECT
            LOWER(tipo) AS tipo,
            COUNT(*) AS total
        FROM imoveis
        WHERE empresa_id=?
        GROUP BY LOWER(tipo)
        ORDER BY total DESC
    """, (empresa_id,))

    rows = cursor.fetchall()

    labels_tipo = []
    dados_tipo = []
    imoveis_por_tipo = []

    casas = 0
    apartamentos = 0
    terrenos = 0

    for row in rows:

        tipo = row["tipo"] or "Não informado"
        total = row["total"]

        labels_tipo.append(tipo.capitalize())
        dados_tipo.append(total)

        percentual = round(
            (total / total_imoveis) * 100,
            1
        ) if total_imoveis else 0

        imoveis_por_tipo.append({
            "tipo": tipo.capitalize(),
            "total": total,
            "percentual": percentual
        })

        if tipo == "casa":
            casas = total

        elif tipo == "apartamento":
            apartamentos = total

        elif tipo == "terreno":
            terrenos = total

    # =====================================================
    # ÚLTIMOS CLIENTES
    # =====================================================

    cursor.execute("""
        SELECT
            nome,
            interesse
        FROM clientes
        WHERE empresa_id=?
        ORDER BY id DESC
        LIMIT 3
    """, (empresa_id,))

    ultimos_clientes = cursor.fetchall()

    conn.close()

    # =====================================================
    # RENDER
    # =====================================================

    return render_template(

        "dashboard_v2.html",

        # Totais
        total_clientes=total_clientes,
        total_imoveis=total_imoveis,
        total_leads=total_leads,
        total_matchs=total_matchs,

        # Crescimento
        crescimento_clientes=pct_clientes,
        crescimento_imoveis=pct_imoveis,
        crescimento_leads=pct_leads,

        # Barras
        progresso_clientes=progresso_clientes,
        progresso_imoveis=progresso_imoveis,
        progresso_leads=progresso_leads,
        progresso_match=progresso_match,

        # Configuração do site
        site=site,

        # Gráfico Clientes
        labels_clientes=labels_clientes,
        dados_clientes=dados_clientes,

        # Gráfico Tipos
        labels_tipo=labels_tipo,
        dados_tipo=dados_tipo,

        # Cards por tipo
        casas=casas,
        apartamentos=apartamentos,
        terrenos=terrenos,

        imoveis_por_tipo=imoveis_por_tipo,

        # Últimos clientes
        ultimos_clientes=ultimos_clientes
    )
 
@app.route("/importar_imoveis_pdf", methods=["POST"])
@verificar_sessao
def importar_imoveis_pdf():

    import json
    import sqlite3


    dados = json.loads(
        request.form["dados"]
    )


    links = json.loads(
        request.form["links"]
    )


    selecionados = request.form.getlist(
        "selecionados"
    )


    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()


    print("TOTAL IMOVEIS:", len(dados))
    print("TOTAL LINKS:", len(links))



    for x in selecionados:


        i = dados[int(x)]



        # ======================
        # CADASTRA IMOVEL
        # ======================

        cursor.execute("""
        INSERT INTO imoveis
        (
        titulo,
        empresa_id,
        tipo,
        valor,
        cidade,
        bairro,
        quartos,
        area,
        status,
        usuario_id,
        rua,
        iptu,
        condominio,
        vaga_garagem
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
        i.get("titulo"),
        session["empresa_id"],
        "Apartamento",
        i.get("valor"),
        "Praia Grande",
        i.get("bairro"),
        i.get("quartos"),
        i.get("area"),
        "Disponível",
        session["usuario_id"],
        i.get("rua"),
        i.get("iptu"),
        i.get("condominio"),
        i.get("vaga")
        ))



        imovel_id = cursor.lastrowid



        print(
            "IMOVEL CRIADO:",
            imovel_id
        )



        # ======================
        # PEGA DRIVE
        # ======================

        link_drive = ""


        if int(x) < len(links):

            link_drive = links[int(x)]



        fotos = []



        if (
            link_drive
            and "drive.google.com" in link_drive
        ):


            fotos = baixar_fotos_drive(
                link_drive,
                imovel_id
            )



        else:

            print(
                "SEM LINK DRIVE"
            )



        # ======================
        # SALVA FOTOS NO BANCO
        # ======================

        for foto in fotos:


            cursor.execute("""
            INSERT INTO fotos_imoveis
            (
            imovel_id,
            nome_arquivo
            )
            VALUES (?,?)
            """,
            (
            imovel_id,
            foto
            ))



            print(
                "FOTO BANCO:",
                foto
            )



    conn.commit()
    conn.close()


    return redirect("/imoveis")


@app.route('/admin/configurar-site', methods=['POST'])
def salvar_configuracoes():
    if not session.get('is_admin'):
        return "Acesso negado", 403
    
    empresa_id = session.get('empresa_id')
    nome = request.form.get('nome_imobiliaria')
    cor = request.form.get('cor_primaria')
    subdominio = request.form.get('subdominio')
    
    # Aqui entraria a lógica de upload da logo (salve apenas o caminho da imagem)
    
    conn = sqlite3.connect('/data/imobiliaria.db')
    cursor = conn.cursor()
    
    # Usamos INSERT OR REPLACE para atualizar se já existir
    cursor.execute("""
        INSERT OR REPLACE INTO configuracoes_site (empresa_id, nome_imobiliaria, cor_primaria, subdominio)
        VALUES (?, ?, ?, ?)
    """, (empresa_id, nome, cor, subdominio))
    
    conn.commit()
    conn.close()
    return "Site configurado com sucesso!"

@app.route("/manutencao")
def manutencao():
    return render_template("manutencao.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        senha = request.form.get("senha")

        if not email or not senha:
            return render_template("login.html", erro="Preencha todos os campos.")

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM usuarios WHERE email = ?
        """, (email,))

        usuario = cursor.fetchone()

        if usuario and check_password_hash(usuario["senha"], senha):

            # gera token de sessão (SaaS segurança)
            novo_token = secrets.token_hex(16)

            cursor.execute("""
                UPDATE usuarios 
                SET session_token = ?
                WHERE id = ?
            """, (novo_token, usuario["id"]))

            conn.commit()
            conn.close()

            # =========================
            # SESSION PADRÃO DO SISTEMA
            # =========================
            session["usuario_id"] = usuario["id"]
            session["empresa_id"] = usuario["empresa_id"]
            session["usuario_nome"] = usuario["nome"]
            session["user_email"] = usuario["email"]
            session["perfil"] = usuario["perfil"]
            session["is_admin"] = usuario["is_admin"]
            session["session_token"] = novo_token

            return redirect("/dashboard_v2")

        conn.close()
        return render_template("login.html", erro="E-mail ou senha incorretos.")

    return render_template("login.html")

@app.route("/cadastrar_usuario", methods=["GET", "POST"])
def cadastrar_usuario():
    if request.method == "POST":
        # Captura os dados do formulário
        nome = request.form.get("nome")
        email = request.form.get("email")
        senha_pura = request.form.get("senha")
        nome_empresa = request.form.get("nome_empresa") or "Sem Nome"

        # Gera o hash da senha para segurança
        senha_hash = generate_password_hash(senha_pura)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            # 1. Cria a empresa e obtém o ID gerado automaticamente
            cursor.execute("INSERT INTO empresas (nome) VALUES (?)", (nome_empresa,))
            empresa_id = cursor.lastrowid

            # 2. Cria o usuário vinculado ao ID da empresa recém-criada
            cursor.execute("INSERT INTO usuarios (nome, email, senha, empresa_id, status_assinatura) VALUES (?, ?, ?, ?, ?)", (nome, email, senha_hash, empresa_id, "ativo"))

            usuario_id = cursor.lastrowid

            cursor.execute("UPDATE usuarios SET whatsapp_sessao = ? WHERE id = ?", (f"corretor_{usuario_id}", usuario_id))
         

            conn.commit()
            print(f"DEBUG: Usuário {email} cadastrado na empresa {nome_empresa} (ID: {empresa_id})")

        except sqlite3.Error as e:
            print(f"DEBUG: Erro no banco de dados: {e}")
            flash("Erro ao cadastrar. Tente novamente.", "danger")
            return redirect("/cadastrar_usuario")
        finally:
            conn.close()

        flash("Conta criada com sucesso! Faça login.", "success")
        return redirect("/login")

    return render_template("cadastrar_usuario.html")



@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/suspenso")
def suspenso():
    return """
    <div style='text-align:center; margin-top:100px; color:white; background:#0b0f19; font-family:sans-serif; height:100vh; padding-top:50px;'>
        <h1>Acesso Suspenso 🛑</h1>
        <p style='color:#9ca3af;'>Sua assinatura SMARTZEN expirou ou foi pausada pelo administrador.</p>
        <a href='/logout' style='color:#0ea5e9; font-weight:bold; text-decoration:none;'>Clique aqui para Sair</a>
    </div>
    """


# ==@app.route("/configuracoes", methods=["GET", "POST"])
@app.route("/configuracoes", methods=["GET", "POST"])
@verificar_sessao
def configuracoes():

    UPLOAD_FOLDER = app.config['UPLOAD_FOLDER_PERFIL']

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":

        nome = request.form.get("nome", "").strip()
        telefone = request.form.get("telefone", "").strip()

        # Atualiza nome e telefone
        cursor.execute("""
            UPDATE usuarios
            SET nome = ?,
                telefone = ?
            WHERE id = ?
            AND empresa_id = ?
        """, (
            nome,
            telefone,
            session["usuario_id"],
            session["empresa_id"]
        ))

        # Foto
        file = request.files.get("foto")

        if file and file.filename != "":

            filename = f"usuario_{session['usuario_id']}.jpg"

            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)

            save_path = os.path.join(
                UPLOAD_FOLDER,
                filename
            )

            file.save(save_path)

            cursor.execute("""
                UPDATE usuarios
                SET foto_url = ?
                WHERE id = ?
                AND empresa_id = ?
            """, (
                f"uploads/perfil/{filename}",
                session["usuario_id"],
                session["empresa_id"]
            ))

        conn.commit()

        return redirect("/configuracoes")

    # usuário
    cursor.execute("""
        SELECT
            nome,
            foto_url,
            is_admin,
            telefone
        FROM usuarios
        WHERE id = ?
        AND empresa_id = ?
    """, (
        session["usuario_id"],
        session["empresa_id"]
    ))

    usuario = cursor.fetchone()

    # empresa / site
    cursor.execute("""
        SELECT *
        FROM configuracoes_site
        WHERE empresa_id = ?
    """, (
        session["empresa_id"],
    ))

    empresa = cursor.fetchone()

    conn.close()

    return render_template(
        "configuracoes.html",
        usuario=usuario,
        empresa=empresa
    )


@app.route("/whatsapp")
def whatsapp():
    return render_template("whatsapp.html")


@app.route("/salvar_logo_imobiliaria", methods=["POST"])
@verificar_sessao
def salvar_logo_imobiliaria():

    arquivo = request.files.get("logo")

    if not arquivo or arquivo.filename == "":
        return redirect("/configuracoes")

    pasta = "/data/uploads/logos"

    if not os.path.exists(pasta):
        os.makedirs(pasta)

    ext = arquivo.filename.rsplit(".", 1)[1].lower()

    nome_arquivo = (
        f"logo_empresa_{session['empresa_id']}.{ext}"
    )

    caminho = os.path.join(
        pasta,
        nome_arquivo
    )

    arquivo.save(caminho)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE configuracoes_site
        SET logo = ?
        WHERE empresa_id = ?
    """, (
        f"/uploads/logos/{nome_arquivo}",
        session["empresa_id"]
    ))
    conn.commit()
    conn.close()

    return redirect("/configuracoes")
# 3. PAINEL ADMINISTRATIVO (CONTROLE DO DONO)
# =========================================

@app.route("/teste_whatsapp")
def teste_whatsapp():
    return render_template("teste_whatsapp.html")

@app.route("/admin")
@verificar_sessao
def admin():
    # 1. Verifica se o usuário é admin da empresa (proteção básica)
    if session.get('is_admin') != 1:
        return "Acesso Negado.", 403

    # 2. SE FOR VOCÊ: Acesso ao painel global completo
    if session.get('user_email') == 'jacksonwillyan8@gmail.com':
        conn = get_db()
        cursor = conn.cursor()
        
        # Métricas globais de todo o sistema
        total_imoveis = cursor.execute("SELECT COUNT(*) FROM imoveis").fetchone()[0]
        total_clientes = cursor.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        
        # Lista de todos os usuários do sistema
        corretores = cursor.execute("SELECT id, nome, email, empresa_id, status_assinatura, validade_assinatura, is_admin FROM usuaris").fetchall()
        
        conn.close()
        return render_template("admin.html", 
                               corretores=corretores, 
                               total_imoveis=total_imoveis, 
                               total_clientes=total_clientes)

    # 3. SE FOR OUTRO ADMIN: Redireciona para o painel restrito da empresa dele
    else:
        # Tente redirecionar para uma rota que não exija permissões especiais
        # ou apenas retorne uma mensagem clara.
        return render_template("acesso_restrito.html")

# Rota para processar as ações (Promover, Bloquear, Resetar Senha)
@app.route("/admin/acao/<int:user_id>", methods=["POST"])
@verificar_sessao
def admin_acao(user_id):
    if session.get('is_admin') != 1:
        return "Acesso Negado.", 403

    acao = request.form.get('acao')

    if acao == 'promover_admin':
        db.execute("UPDATE usuarios SET is_admin = 1 WHERE id = ?", (user_id,))
    elif acao == 'bloquear':
        db.execute("UPDATE usuarios SET status_assinatura = 'bloqueado' WHERE id = ?", (user_id,))
    elif acao == 'ativar':
        db.execute("UPDATE usuarios SET status_assinatura = 'ativo' WHERE id = ?", (user_id,))
    elif acao == 'resetar_senha':
        nova_senha = request.form.get('nova_senha')
        db.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (nova_senha, user_id))

    db.commit()
    return redirect(url_for('admin'))



@app.route("/admin/bloquear/<int:id>")
def admin_bloquear(id):
    if session.get("is_admin") != 1:
        return "Negado", 403
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET status_assinatura='bloqueado' WHERE id=?", (id,)
    )
    conn.commit()
    conn.close()
    return redirect("/admin")


@app.route('/admin/criar-login', methods=['POST'])
def criar_login():

    if not session.get('is_admin'):
        return "Acesso negado", 403

    email = request.form.get('email')
    senha_raw = request.form.get('senha')
    nome = request.form.get('nome')
    telefone = request.form.get('telefone')
    empresa_id = session.get('empresa_id')

    senha_hash = generate_password_hash(senha_raw)

    conn = sqlite3.connect('/data/imobiliaria.db')
    cursor = conn.cursor()

    try:

        # Cria usuário
        cursor.execute("""
            INSERT INTO usuarios
            (
                email,
                senha,
                telefone,
                empresa_id,
                nome
            )
            VALUES (?, ?, ?, ?, ?)
        """,
        (
            email,
            senha_hash,
            telefone,
            empresa_id,
            nome
        ))

        # ID gerado
        usuario_id = cursor.lastrowid

        # Cria sessão WhatsApp automática
        whatsapp_sessao = f"corretor_{usuario_id}"

        cursor.execute("""
            UPDATE usuarios
            SET whatsapp_sessao = ?
            WHERE id = ?
        """,
        (
            whatsapp_sessao,
            usuario_id
        ))

        conn.commit()

        print(
            f"Usuário criado: {nome} | Sessão: {whatsapp_sessao}"
        )

        return redirect("/admin/novo-usuario")

    except Exception as e:

        conn.rollback()

        print("ERRO:", e)

        return f"Erro ao criar usuário: {e}"

    finally:

        conn.close()



@app.route('/admin/novo-usuario')
def exibir_novo_usuario():

    empresa_id = session.get('empresa_id')

    if not empresa_id:
        return "Acesso negado: você não está logado como empresa.", 403

    conn = sqlite3.connect('/data/imobiliaria.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nome, email, ativo
        FROM usuarios
        WHERE empresa_id = ?
    """, (empresa_id,))

    usuarios_db = cursor.fetchall()

    conn.close()

    lista_usuarios = [
        {
            "id": u[0],
            "nome": u[1],
            "email": u[2],
            "ativo": u[3]
        }
        for u in usuarios_db
    ]

    return render_template(
        'novo-usuario.html',
        usuarios=lista_usuarios
    )
@app.route("/admin/liberar/<int:id>", methods=["POST"])
def admin_liberar(id):
    if session.get("is_admin") != 1:
        return "Negado", 403
    nova_data = request.form["validade"]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET status_assinatura='ativo', validade_assinatura=? WHERE id=?",
        (nova_data, id),
    )
    conn.commit()
    conn.close()
    return redirect("/admin")



@app.route("/admin/resetar_senha/<int:id>", methods=["POST"])
def admin_resetar_senha(id):
    # Verificação de segurança: Apenas admins podem acessar
    if session.get("is_admin") != 1:
        return "Acesso negado", 403

    nova_senha_plain = request.form["nova_senha"]
    # SEMPRE HASH: Nunca guarde senhas em texto puro no banco
    senha_hash = generate_password_hash(nova_senha_plain)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Atualização com segurança extra:
    # Mesmo como admin, garantimos que o ID do usuário é válido
    cursor.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (senha_hash, id))

    # Se você quiser garantir que o admin só mude senhas da própria empresa, 
    # bastaria adicionar: AND empresa_id = ? (pegando da sessão do admin)

    conn.commit()
    conn.close()

    flash("Senha alterada com sucesso!", "success")
    return redirect("/admin")


# ==========================================
# 4. ROTAS DE CLIENTE


@app.route("/cadastrar_cliente", methods=["GET", "POST"])
@verificar_sessao
def cadastrar_cliente():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == "POST":

        nome = request.form["nome"]
        telefone = request.form["telefone"]
        interesse = request.form["interesse"]
        faixa_preco = request.form["faixa_preco"]
        bairro = request.form.get("bairro", "")
        sobre = request.form.get("sobre", "")
        entrada = request.form.get("entrada", "")
        pagamento = request.form.get("pagamento", "")
        origem = request.form.get("origem", "")
        empreendimento = request.form.get("empreendimento", "")
        construtora = request.form.get("construtora", "")

        user_id = session["usuario_id"]
        empresa_id = session["empresa_id"]

        data_criacao = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO clientes (
                nome,
                telefone,
                interesse,
                faixa_preco,
                bairro,
                sobre,
                entrada,
                pagamento,
                origem,
                empreendimento,
                construtora,
                usuario_id,
                empresa_id,
                data_criacao
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nome,
            telefone,
            interesse,
            faixa_preco,
            bairro,
            sobre,
            entrada,
            pagamento,
            origem,
            empreendimento,
            construtora,
            user_id,
            empresa_id,
            data_criacao
        ))

        conn.commit()
        conn.close()

        return redirect("/clientes")

    # =========================
    # GET (LISTAGEM OU FORM)
    # =========================

    cursor.execute("""
        SELECT 
            c.*,
            u.nome AS nome_criador
        FROM clientes c
        LEFT JOIN usuarios u ON u.id = c.usuario_id
        WHERE c.empresa_id = ?
        ORDER BY c.id DESC
    """, (session["empresa_id"],))

    clientes = cursor.fetchall()

    conn.close()

    return render_template(
        "cadastrar_cliente.html",
        clientes=clientes
    )
# ==========================================
# 5. ROTAS DE IMÓVEIS
# ==========================================
@app.route("/converter_lead/<int:lead_id>")
@verificar_sessao
def converter_lead(lead_id):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM lead_site
        WHERE id = ?
    """, (lead_id,))

    lead = cursor.fetchone()

    if lead:

        cursor.execute("""
            INSERT INTO clientes
            (
                nome,
                telefone,
                email,
                interesse,
                faixa_preco,
                bairro,
                sobre,
                entrada,
                pagamento,
                usuario_id,
                empresa_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead["nome"],
            lead["telefone"],
            "",
            "",
            "",
            "",
            lead["mensagem"] if "mensagem" in lead.keys() else "",
            "",
            "",
            session["usuario_id"],
            session["empresa_id"]
        ))

        cursor.execute("""
            DELETE FROM lead_site
            WHERE id = ?
        """, (lead_id,))

        conn.commit()

    conn.close()

    flash("Lead adicionado ao sistema com sucesso!")

    return redirect("/leads_site")

@app.route("/imoveis")
@verificar_sessao
def imoveis():
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()

    # 1. Busca apenas os imóveis desta empresa específica
    cursor.execute("SELECT * FROM imoveis WHERE empresa_id = ?", (empresa_id,))
    imoveis_db = cursor.fetchall()

    lista_final = []
    for row in imoveis_db:
        imovel = dict(row)
        # 2. Busca as fotos vinculadas ao imóvel (o imovel_id já é único/seguro)
        cursor.execute("SELECT nome_arquivo FROM fotos_imoveis WHERE imovel_id = ?", (imovel['id'],))
        fotos = [r['nome_arquivo'] for r in cursor.fetchall()]
        imovel['fotos'] = fotos
        lista_final.append(imovel)

    conn.close()
    return render_template("imoveis.html", imoveis=lista_final)


@app.route("/excluir_imovel/<int:id>")
@verificar_sessao
def excluir_imovel(id):
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Buscamos o imóvel apenas se ele pertencer à empresa logada
    cursor.execute("SELECT foto FROM imoveis WHERE id=? AND empresa_id=?", (id, empresa_id))
    resultado = cursor.fetchone()

    if resultado and resultado[0]:
        foto_nome = resultado[0]
        caminho_foto = os.path.join(app.config['UPLOAD_FOLDER_IMOVEIS'], foto_nome)

        # Apaga o arquivo físico da pasta
        if os.path.exists(caminho_foto):
            os.remove(caminho_foto)

    # 2. Excluímos o registro do banco de dados com segurança
    cursor.execute("DELETE FROM imoveis WHERE id=? AND empresa_id=?", (id, empresa_id))
    conn.commit()
    conn.close()

    flash("Imóvel excluído com sucesso!", "success")
    return redirect("/imoveis")


# --- ROTA DE DETALHES UNIFICADA (Substitua as antigas por esta) ---

@app.route("/imovel/<int:imovel_id>")
@app.route("/detalhes_imovel/<int:imovel_id>")
@verificar_sessao # Usando o decorador de segurança unificado
def ver_imovel(imovel_id):
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()

    # 1. Busca o imóvel filtrando pela empresa_id
    cursor.execute("""
        SELECT * FROM imoveis 
        WHERE id = ? AND empresa_id = ?
    """, (imovel_id, empresa_id))
    imovel_row = cursor.fetchone()

    if not imovel_row:
        conn.close()
        return "Imóvel não encontrado ou sem permissão de acesso.", 404

    imovel = dict(imovel_row)

    # 2. Busca todas as fotos deste imóvel
    # Como o imovel_id é único, a segurança já foi validada no passo acima
    cursor.execute("SELECT nome_arquivo FROM fotos_imoveis WHERE imovel_id = ?", (imovel_id,))
    fotos = [row['nome_arquivo'] for row in cursor.fetchall()]

    imovel['fotos'] = fotos
    conn.close()

    return render_template("detalhes_imovel.html", imovel=imovel)


@app.route("/funil")
@verificar_sessao
def funil():

    empresa_id = session.get("empresa_id")

    # ==========================
    # FILTROS
    # ==========================

    pesquisa = request.args.get("pesquisa", "").strip()
    corretor = request.args.get("corretor", "")
    origem = request.args.get("origem", "")
    empreendimento = request.args.get("empreendimento", "")
    data_inicio = request.args.get("data_inicio", "")
    data_fim = request.args.get("data_fim", "")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ==========================
    # CONSULTA PRINCIPAL
    # ==========================

    sql = """
        SELECT
            c.*,
            u.nome AS nome_corretor,
            u_cria.nome AS nome_criador

        FROM clientes c

        LEFT JOIN usuarios u
            ON u.id = c.atendido_por
            
        LEFT JOIN usuarios u_cria
            ON u_cria.id = c.usuario_id    

        WHERE c.empresa_id = ?
    """

    parametros = [empresa_id]

    # Pesquisa
    if pesquisa:
        sql += """
            AND (
                c.nome LIKE ?
                OR c.telefone LIKE ?
            )
        """
        parametros.extend([
            f"%{pesquisa}%",
            f"%{pesquisa}%"
        ])

    # Corretor
    if corretor:
        sql += " AND c.atendido_por = ? "
        parametros.append(corretor)

    # Origem
    if origem:
        sql += " AND c.origem = ? "
        parametros.append(origem)

    # Empreendimento
    if empreendimento:
        sql += " AND c.empreendimento = ? "
        parametros.append(empreendimento)

    # Data inicial
    if data_inicio:
        sql += " AND DATE(c.data_criacao) >= DATE(?) "
        parametros.append(data_inicio)

    # Data final
    if data_fim:
        sql += " AND DATE(c.data_criacao) <= DATE(?) "
        parametros.append(data_fim)

    sql += " ORDER BY c.id DESC "

    cursor.execute(sql, parametros)

    clientes = cursor.fetchall()

    # ==========================
    # LISTA DE CORRETORES
    # ==========================

    cursor.execute("""
        SELECT id, nome
        FROM usuarios
        WHERE empresa_id = ?
        ORDER BY nome
    """, (empresa_id,))

    corretores = cursor.fetchall()

    # ==========================
    # ORIGENS
    # ==========================

    cursor.execute("""
        SELECT DISTINCT origem
        FROM clientes
        WHERE empresa_id = ?
        AND origem IS NOT NULL
        AND origem <> ''
        ORDER BY origem
    """, (empresa_id,))

    origens = [x["origem"] for x in cursor.fetchall()]

    # ==========================
    # EMPREENDIMENTOS
    # ==========================

    cursor.execute("""
        SELECT DISTINCT empreendimento
        FROM clientes
        WHERE empresa_id = ?
        AND empreendimento IS NOT NULL
        AND empreendimento <> ''
        ORDER BY empreendimento
    """, (empresa_id,))

    empreendimentos = [x["empreendimento"] for x in cursor.fetchall()]

    conn.close()

    # ==========================
    # ETAPAS
    # ==========================

    etapas = [
        "Lead Novo",
        "Visita Agendada",
        "Negociação",
        "Concluido",
        "Desistencia"
    ]

    funil_dados = {
        etapa: []
        for etapa in etapas
    }

    for cliente in clientes:

        status = cliente["status_funil"] or "Lead Novo"

        if status not in funil_dados:
            status = "Lead Novo"

        funil_dados[status].append(cliente)

    # ==========================
    # INDICADORES
    # ==========================

    total_leads = len(clientes)
    atendimento = len(funil_dados["Lead Novo"])
    visitas = len(funil_dados["Visita Agendada"])
    propostas = len(funil_dados["Negociação"])
    vendas = len(funil_dados["Concluido"])

    return render_template(
        "funil.html",
        funil_dados=funil_dados,
        etapas=etapas,

        corretores=corretores,
        origens=origens,
        empreendimentos=empreendimentos,

        total_leads=total_leads,
        atendimento=atendimento,
        visitas=visitas,
        propostas=propostas,
        vendas=vendas,

        pesquisa=pesquisa,
        corretor=corretor,
        origem=origem,
        empreendimento=empreendimento,
        data_inicio=data_inicio,
        data_fim=data_fim
    )

@app.route("/editar_imovel/<int:id>", methods=["GET", "POST"])
@verificar_sessao
def editar_imovel(id):
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":

        titulo = request.form.get("titulo", "")
        tipo = request.form.get("tipo", "Casa")
        valor = request.form.get("valor", 0)
        cidade = request.form.get("cidade", "")
        bairro = request.form.get("bairro", "")
        quartos = request.form.get("quartos") or 0
        banheiros = request.form.get("banheiros") or 0
        area = request.form.get("area") or 0
        status = request.form.get("status", "Venda")
        descricao = request.form.get("descricao", "")
        condominio = request.form.get("condominio", "")
        link = request.form.get("link", "")
        cep = request.form.get("cep", "")
        lavabo  = request.form.get("lavabo", "")
        vaga_garagem = request.form.get("vaga_garagem", "")
        lazer = request.form.get("lazer", "")
        sacada = request.form.get("sacada", "")
        rua = request.form.get("rua", "")
        iptu = request.form.get("iptu", "")
        parcela = request.form.get("parcela", "")
        prazo = request.form.get("prazo", "")
        anuais = request.form.get("anuais", "")
        entrada = request.form.get("entrada", "")
        banheiros21 = request.form.get("banheiros21", "")
        proprietario1 = request.form.get("proprietario1", "")
        telefone2 = request.form.get("telefone2", "")
        mobilia = request.form.get("mobilia", "")
        compartilhar_fifit = int(request.form.get("compartilhar_fifit", 0))

        # Atualiza os dados do imóvel
        cursor.execute("""
            UPDATE imoveis
            SET titulo=?,
                tipo=?,
                valor=?,
                cidade=?,
                bairro=?,
                quartos=?,
                banheiros=?,
                area=?,
                status=?,
                descricao=?,
                condominio=?,
                link=?,
                cep=?,
                lavabo=?,                
                vaga_garagem=?,
                lazer=?,
                sacada=?,
                rua=?,
                iptu=?,
                parcela=?,
                prazo=?,
                anuais=?,
                entrada=?,
                banheiros21=?,
                proprietario1=?,
                telefone2=?,
                mobilia=?,
                compartilhar_fifit=?
            WHERE id=? AND empresa_id=?
        """, (
            titulo,
            tipo,
            valor,
            cidade,
            bairro,
            quartos,
            banheiros,
            area,
            status,
            descricao,
            condominio,
            link,
            cep,
            lavabo,
            vaga_garagem,
            lazer,
            sacada,
            rua,
            iptu,
            parcela,
            prazo,
            anuais,
            entrada,
            banheiros21,
            proprietario1,
            telefone2,
            mobilia,
            compartilhar_fifit,
            id,
            empresa_id
        ))

        # ==========================
        # NOVAS FOTOS
        # ==========================
        arquivos = request.files.getlist("fotos[]")

        for file in arquivos:

            if file and file.filename != "":

                nome_seguro = secure_filename(file.filename)

                nome_foto = (
                    f"{id}_"
                    f"{int(datetime.now().timestamp())}_"
                    f"{nome_seguro}"
                )

                caminho_salvamento = os.path.join(
                    app.config["UPLOAD_FOLDER_IMOVEIS"],
                    nome_foto
                )

                file.save(caminho_salvamento)

                cursor.execute("""
                    INSERT INTO fotos_imoveis
                    (imovel_id, nome_arquivo)
                    VALUES (?, ?)
                """, (
                    id,
                    nome_foto
                ))

        conn.commit()
        conn.close()

        return redirect("/imoveis")

    # ==========================
    # BUSCAR IMÓVEL
    # ==========================
    cursor.execute("""
        SELECT *
        FROM imoveis
        WHERE id=? AND empresa_id=?
    """, (id, empresa_id))

    imovel = cursor.fetchone()

    if not imovel:
        conn.close()
        return "Imóvel não encontrado ou sem permissão de acesso.", 404

    # ==========================
    # BUSCAR FOTOS
    # ==========================
    cursor.execute("""
        SELECT *
        FROM fotos_imoveis
        WHERE imovel_id=?
        ORDER BY id DESC
    """, (id,))

    fotos = cursor.fetchall()

    conn.close()

    return render_template(
        "editar_imovel.html",
        imovel=imovel,
        fotos=fotos
    )



@app.route("/gerar_site")
def gerar_site():

    empresa_id = session["empresa_id"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # busca empresa
    cursor.execute("""
        SELECT * FROM empresas WHERE id = ?
    """, (empresa_id,))

    empresa = cursor.fetchone()

    conn.close()

    return render_template(
        "gerar_site.html",
        empresa=empresa
    )
# ==========================================
# 6. INTELIGÊNCIA ARTIFICIAL / ANÚNCIOS
# ==========================================

@app.route("/gerar_site/salvar", methods=["POST"])
def salvar_site():

    import re
    import sqlite3

    empresa_id = session["empresa_id"]


    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()



    # verifica se já existe site da empresa

    cursor.execute("""
        SELECT *
        FROM configuracoes_site
        WHERE empresa_id = ?
    """,(empresa_id,))


    site = cursor.fetchone()


    if site:

        conn.close()

        return redirect("/dashboard_v2")




    # busca nome da empresa

    cursor.execute("""
        SELECT nome
        FROM empresas
        WHERE id = ?
    """,(empresa_id,))


    empresa = cursor.fetchone()



    nome = empresa["nome"]



    # cria slug automático

    slug = re.sub(
        r'[^a-z0-9]+',
        '-',
        nome.lower()
    ).strip("-")



    cor = "#22c55e"



    cursor.execute("""
        INSERT INTO configuracoes_site
        (
        empresa_id,
        nome_imobiliaria,
        cor_primaria,
        subdominio
        )
        VALUES (?,?,?,?)
    """,
    (
        empresa_id,
        nome,
        cor,
        slug
    ))



    conn.commit()
    conn.close()



    return redirect(f"/site/{slug}")


@app.route("/gerar_anuncio", methods=["GET", "POST"])
@verificar_sessao
def gerar_anuncio():
    empresa_id = session.get("empresa_id")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Busca imóveis da empresa
    cursor.execute("SELECT * FROM imoveis WHERE empresa_id=?", (empresa_id,))
    lista_imoveis = cursor.fetchall()

    anuncio, imovel_selecionado = None, None

    if request.method == "POST":
        id_imovel = request.form["imovel_id"]

        cursor.execute(
            "SELECT * FROM imoveis WHERE id=? AND empresa_id=?",
            (id_imovel, empresa_id),
        )
        imovel_selecionado = cursor.fetchone()

        if imovel_selecionado:
            try:
                # Montagem do prompt com os dados do imóvel
                prompt = prompt = f"""
Crie um anúncio de venda imobiliária atraente e persuasivo para o imóvel abaixo.

REGRAS IMPORTANTES:
1. NÃO use asteriscos (*), hashtags (#) ou qualquer caractere de formatação Markdown.
2. Use apenas texto simples, quebras de linha e emojis nativos para organizar o texto.
3. Estruture o anúncio com: Título chamativo, lista de benefícios, valor e um convite para ação (Call-to-Action).
4. Mantenha um tom profissional e entusiasmado.

DADOS DO IMÓVEL:
{imovel_selecionado}

Gere o anúncio agora:"""

                
                # Chamada direta usando o objeto 'model' configurado no topo
                response = model.generate_content(prompt)
                anuncio = response.text
                
            except Exception as e:
                anuncio = f"Erro ao conectar com a IA: {e}"

    conn.close()
    return render_template(
        "gerar_anuncio.html",
        imoveis=lista_imoveis,
        anuncio=anuncio,
        imovel=imovel_selecionado,
    )
@app.route("/cliente/<int:id>")
@verificar_sessao
def perfil_cliente(id):

    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ==========================
    # CLIENTE
    # ==========================

    cursor.execute("""
        SELECT
            c.*,
            u.nome AS nome_corretor
        FROM clientes c
        LEFT JOIN usuarios u
            ON u.id = c.atendido_por
        WHERE c.id = ?
        AND c.empresa_id = ?
    """, (id, empresa_id))

    cliente = cursor.fetchone()

    if not cliente:
        conn.close()
        return "Cliente não encontrado ou não pertence a esta empresa.", 404


    # ==========================
    # OCORRÊNCIAS
    # ==========================

    cursor.execute("""
        SELECT
            o.*,
            u.nome as usuario_nome
        FROM ocorrencias_clientes o
        LEFT JOIN usuarios u
            ON u.id = o.usuario_id
        WHERE o.cliente_id = ?
        ORDER BY o.id DESC
    """, (id,))

    ocorrencias = cursor.fetchall()


    # ==========================
    # HISTÓRICO
    # ==========================

    cursor.execute("""
        SELECT
            h.*,
            u.nome AS nome_usuario
        FROM cliente_historico h
        LEFT JOIN usuarios u
            ON u.id = h.usuario_id
        WHERE h.cliente_id = ?
        ORDER BY h.id DESC
    """, (id,))

    historico = cursor.fetchall()


    # ==========================
    # IMÓVEIS DA EMPRESA
    # ==========================

    cursor.execute("""
        SELECT
            id,
            titulo,
            tipo,
            valor,
            cidade,
            bairro,
            foto
        FROM imoveis
        WHERE empresa_id = ?
    """, (empresa_id,))

    imoveis = cursor.fetchall()

    conn.close()


    # ==========================
    # MATCH IA
    # ==========================

    matches_cliente = []

    c_interesse = cliente["interesse"]
    c_faixa = cliente["faixa_preco"]
    c_bairro = cliente["bairro"]

    c_bairro_txt = (
        str(c_bairro).lower().strip()
        if c_bairro else ""
    )

    interesse_txt = (
        str(c_interesse).lower().strip()
        if c_interesse else ""
    )


    for i in imoveis:

        i_id = i["id"]
        i_titulo = i["titulo"]
        i_valor = i["valor"]
        i_bairro = i["bairro"]
        i_cidade = i["cidade"]
        i_foto = i["foto"]

        i_bairro_txt = (
            str(i_bairro).lower().strip()
            if i_bairro else ""
        )

        porcentagem = 0

        if (
            i_bairro_txt and
            (
                i_bairro_txt == c_bairro_txt
                or i_bairro_txt in interesse_txt
            )
        ):
            porcentagem += 50


        try:

            imovel_num = float(
                ''.join(
                    filter(
                        str.isdigit,
                        str(i_valor)
                    )
                )
            )

            cliente_num = float(
                ''.join(
                    filter(
                        str.isdigit,
                        str(c_faixa)
                    )
                )
            )

            if imovel_num <= (cliente_num * 1.10):
                porcentagem += 50

        except:

            if (
                c_faixa and
                str(i_valor).strip()
                in str(c_faixa).strip()
            ):
                porcentagem += 50


        if porcentagem >= 50:

            matches_cliente.append({
                "id": i_id,
                "titulo": i_titulo,
                "valor": i_valor,
                "local": f"{i_bairro}, {i_cidade}",
                "foto": i_foto,
                "porcentagem": porcentagem
            })


    return render_template(
        "perfil_cliente.html",
        cliente=cliente,
        matches=matches_cliente,
        ocorrencias=ocorrencias,
        historico=historico
    )



@app.route(
    "/cliente/adicionar_ocorrencia/<int:cliente_id>",
    methods=["POST"]
)
@verificar_sessao
def adicionar_ocorrencia(cliente_id):

    ocorrencia = request.form.get("ocorrencia")
    usuario_id = session["usuario_id"]

    if ocorrencia and ocorrencia.strip():

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ocorrencias_clientes
            (
                cliente_id,
                usuario_id,
                ocorrencia
            )
            VALUES (?, ?, ?)
        """, (
            cliente_id,
            usuario_id,
            ocorrencia
        ))

        conn.commit()
        conn.close()

    return redirect(f"/cliente/{cliente_id}")

@app.route("/cliente/atualizar_status/<int:id>", methods=["POST"])
@verificar_sessao
def atualizar_status_cliente(id):

    novo_status = request.form.get("status_funil")
    data_visita = request.form.get("data_visita")

    empresa_id = session.get("empresa_id")
    usuario_id = session.get("usuario_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Atualiza cliente
    cursor.execute("""
        UPDATE clientes
        SET
            status_funil = ?,
            data_visita = ?,
            atendido_por = ?
        WHERE id = ?
        AND empresa_id = ?
    """,
    (
        novo_status,
        data_visita,
        usuario_id,
        id,
        empresa_id
    ))


    # Grava histórico
    cursor.execute("""
        INSERT INTO cliente_historico
        (
            cliente_id,
            usuario_id,
            status,
            observacao
        )
        VALUES (?,?,?,?)
    """,
    (
        id,
        usuario_id,
        novo_status,
        "Status alterado"
    ))


    conn.commit()
    conn.close()

    return redirect(f"/cliente/{id}")



@app.route("/cliente/atualizar_dados/<int:id>", methods=["POST"])
@verificar_sessao
def atualizar_dados_cliente(id):

    nome = request.form.get("nome")
    telefone = request.form.get("telefone")
    email = request.form.get("email")
    cpf = request.form.get("cpf")
    endereco = request.form.get("endereco")
    bairro = request.form.get("bairro")
    interesse = request.form.get("interesse")
    faixa_preco = request.form.get("faixa_preco")
    entrada = request.form.get("entrada")
    pagamento = request.form.get("pagamento")
    origem = request.form.get("origem")
    sobre = request.form.get("sobre")

    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clientes
        SET
            nome = ?,
            telefone = ?,
            email = ?,
            cpf = ?,
            endereco = ?,
            bairro = ?,
            interesse = ?,
            faixa_preco = ?,
            entrada = ?,
            pagamento = ?,
            origem = ?,
            sobre = ?
        WHERE id = ?
        AND empresa_id = ?
    """, (
        nome,
        telefone,
        email,
        cpf,
        endereco,
        bairro,
        interesse,
        faixa_preco,
        entrada,
        pagamento,
        origem,
        sobre,
        id,
        empresa_id
    ))

    conn.commit()
    conn.close()

    return redirect(f"/cliente/{id}")


@app.route("/informa-imovel/<int:imovel_id>")
def informa_imovel(imovel_id):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()


    # ==========================
    # IMÓVEL PRINCIPAL
    # ==========================

    cursor.execute("""
        SELECT *
        FROM imoveis
        WHERE id = ?
    """, (imovel_id,))


    imovel = cursor.fetchone()


    if not imovel:

        conn.close()

        return "Imóvel não encontrado",404



    imovel = dict(imovel)





    # ==========================
    # FOTOS DO IMÓVEL
    # ==========================


    cursor.execute("""
        SELECT nome_arquivo
        FROM fotos_imoveis
        WHERE imovel_id = ?
        ORDER BY id ASC
    """,(imovel_id,))


    fotos = cursor.fetchall()



    imovel["fotos"] = [

        foto["nome_arquivo"]

        for foto in fotos

    ]







    # ==========================
    # IMÓVEIS SEMELHANTES
    # ==========================


    semelhantes=[]



    cursor.execute("""
        SELECT *
        FROM imoveis
        WHERE id != ?
        AND empresa_id = ?
        ORDER BY RANDOM()
        LIMIT 6
    """,
    (
        imovel_id,
        imovel.get("empresa_id")
    ))



    semelhantes_db = cursor.fetchall()





    for item in semelhantes_db:


        item = dict(item)



        cursor.execute("""
            SELECT nome_arquivo
            FROM fotos_imoveis
            WHERE imovel_id = ?
            ORDER BY id ASC
            LIMIT 1
        """,
        (item["id"],))



        foto = cursor.fetchone()



        if foto:

            item["foto"] = foto["nome_arquivo"]

        else:

            item["foto"] = None




        semelhantes.append(item)







    # ==========================
    # EMPRESA / HEADER
    # ==========================


    empresa = None



    cursor.execute("""
        SELECT *
        FROM configuracoes_site
        WHERE empresa_id = ?
        LIMIT 1
    """,
    (
        imovel.get("empresa_id"),
    ))



    empresa_db = cursor.fetchone()




    if empresa_db:


        empresa = dict(empresa_db)



    else:


        empresa = {

            "nome_imobiliaria":"SMARTZEN IMOB",

            "logo":None

        }







    conn.close()






    return render_template(

        "informa_imovel.html",

        imovel=imovel,

        semelhantes=semelhantes,

        empresa=empresa

    )



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)

