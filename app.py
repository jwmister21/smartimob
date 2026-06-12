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
from moviepy.video.VideoClip import ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.VideoClip import TextClip
from moviepy.audio.io.AudioFileClip import AudioFileClip 
from moviepy.video.VideoClip import ImageClip# Se precisar de outros, adicione aqui
from moviepy import concatenate_videoclips
import google.generativeai as genai
import json
from openai import OpenAI
from flask import send_from_directory




app = Flask(__name__)
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
    # Pega a data de hoje formatada como 'YYYY-MM-DD'
    hoje = datetime.now().strftime('%Y-%m-%d')

    conn = get_db()

    # Busca clientes onde a data_visita é hoje
    lembretes = conn.execute(
        "SELECT * FROM clientes WHERE date(data_visita) = ?",
        (hoje,)
    ).fetchall()

    conn.close()

    return dict(lembretes=lembretes)


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
        "ALTER TABLE clientes ADD COLUMN status_funil TEXT DEFAULT 'Novo Contato'",
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


@app.route('/uploads/imoveis/<filename>')
def foto_imovel(filename):
    return send_from_directory(
        '/data/uploads/imoveis',
        filename
    )



@app.route("/enviar_imovel/<int:imovel_id>/<telefone>")
@verificar_sessao
def enviar_imovel(imovel_id, telefone):

    import requests
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Busca o imóvel
    cursor.execute(
        "SELECT * FROM imoveis WHERE id = ?",
        (imovel_id,)
    )

    imovel = cursor.fetchone()

    if not imovel:
        conn.close()
        return "Imóvel não encontrado"

    # Busca a primeira foto do imóvel
    cursor.execute("""
        SELECT nome_arquivo
        FROM fotos_imoveis
        WHERE imovel_id = ?
        LIMIT 1
    """, (imovel_id,))

    foto = cursor.fetchone()

    conn.close()

    if not foto:
        return "Imóvel sem fotos cadastradas"

    imagem = (
        request.host_url.rstrip("/")
        + "/uploads/imoveis/"
        + foto["nome_arquivo"]
    )

    print("FOTO:", foto["nome_arquivo"])
    print("URL IMAGEM:", imagem)

    legenda = f"""
🏡 {imovel['titulo']}

💰 Valor: {imovel['valor']}

📍 {imovel['bairro']} - {imovel['cidade']}

🛏 {imovel['quartos']} quartos
🚿 {imovel['banheiros']} banheiros
🚗 {imovel['vaga_garagem']} vagas

📐 Área: {imovel['area']}

{imovel['descricao'] or ''}

🔗 {imovel['link'] or ''}
"""

    numero = telefone.replace(" ", "").replace("-", "")

    if "@c.us" not in numero:
        numero += "@c.us"

    r = requests.post(
        "https://zoom-leggings-viability.ngrok-free.dev/enviar-imagem",
        json={
            "sessao": f"corretor_{session['usuario_id']}",
            "numero": numero,
            "imagem": imagem,
            "legenda": legenda
        }
    )

    print("RESPOSTA NODE:", r.text)

    return r.text

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




@app.route("/buscar_qr")
def buscar_qr():

    usuario_id = session["usuario_id"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT whatsapp_sessao FROM usuarios WHERE id=?",
        (usuario_id,)
    )

    usuario = cursor.fetchone()

    conn.close()

    r = requests.get(
        f"https://zoom-leggings-viability.ngrok-free.dev/qr/{usuario['whatsapp_sessao']}"
    )

    return r.json()

@app.route("/admin/gestao")
@verificar_sessao
@admin_required
def tela_gestao():

    empresa_id = session.get("empresa_id")

    conn = get_db()
    cursor = conn.cursor()

    # Total de usuários
    cursor.execute("""
        SELECT COUNT(*)
        FROM usuarios
        WHERE empresa_id = ?
    """, (empresa_id,))
    total_usuarios = cursor.fetchone()[0]

    # Total de imóveis
    cursor.execute("""
        SELECT COUNT(*)
        FROM imoveis
        WHERE empresa_id = ?
    """, (empresa_id,))
    total_imoveis = cursor.fetchone()[0]

    # Total de clientes
    try:
        cursor.execute("""
            SELECT COUNT(*)
            FROM clientes
            WHERE empresa_id = ?
        """, (empresa_id,))
        total_clientes = cursor.fetchone()[0]
    except:
        total_clientes = 0

    # Imóveis disponíveis
    cursor.execute("""
        SELECT COUNT(*)
        FROM imoveis
        WHERE empresa_id = ?
        AND status = 'Venda'
    """, (empresa_id,))
    imoveis_disponiveis = cursor.fetchone()[0]

    # Imóveis fechados
    cursor.execute("""
        SELECT COUNT(*)
        FROM imoveis
        WHERE empresa_id = ?
        AND status <> 'Venda'
    """, (empresa_id,))
    imoveis_fechados = cursor.fetchone()[0]

    # Ranking de corretores
    cursor.execute("""
        SELECT
            u.id,
            u.nome,
            COUNT(i.id) AS total_imoveis
        FROM usuarios u
        LEFT JOIN imoveis i
            ON u.id = i.usuario_id
        WHERE u.empresa_id = ?
        GROUP BY u.id, u.nome
        ORDER BY total_imoveis DESC
    """, (empresa_id,))

    corretores = cursor.fetchall()

    conn.close()

    return render_template(
        "gestao.html",
        total_usuarios=total_usuarios,
        total_imoveis=total_imoveis,
        total_clientes=total_clientes,
        imoveis_disponiveis=imoveis_disponiveis,
        imoveis_fechados=imoveis_fechados,
        corretores=corretores
    )


# Decorator para o Super Admin
def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Apenas você (Super Admin) acessa
        if session.get('email') != 'seuemail@smartzen.com':
            return "Acesso Negado!", 403
        return f(*args, **kwargs)
    return decorated_function

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


@app.route('/analisar_cliente', methods=['POST'])
def analisar_cliente():
    import json

    dados = request.get_json()
    msg = dados.get('mensagem', '').strip()

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """
Você é um extrator de informações imobiliárias.

Extraia da mensagem:

- bairro
- valor
- quartos
- tipo

Tipos possíveis:
- casa
- apartamento
- sobrado
- terreno
- comercial

Responda SOMENTE JSON.

Exemplo:

{
    "bairro": "Guaianases",
    "valor": 450000,
    "quartos": 3,
    "tipo": "casa"
}

Se algum campo não for informado:

{
    "bairro": "",
    "valor": 999999999,
    "quartos": 0,
    "tipo": ""
}
"""
                },
                {
                    "role": "user",
                    "content": msg
                }
            ]
        )

        texto_limpo = (
            response.choices[0]
            .message.content
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        print("RESPOSTA IA:", texto_limpo)

        filtros = json.loads(texto_limpo)

    except json.JSONDecodeError:
        return jsonify({
            "resultado": "<p>Não consegui interpretar sua busca.</p>"
        })

    except Exception as e:
        print("ERRO IA:", str(e))

        return jsonify({
            "resultado": "<p>Erro ao processar a IA.</p>"
        })

    bairro = filtros.get("bairro", "").strip()
    tipo = filtros.get("tipo", "").strip().lower()

    try:
        quartos = int(filtros.get("quartos", 0))
    except:
        quartos = 0

    try:
        valor_busca = float(filtros.get("valor", 999999999))
    except:
        valor_busca = 999999999

    print("BAIRRO:", bairro)
    print("TIPO:", tipo)
    print("QUARTOS:", quartos)
    print("VALOR:", valor_busca)

    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT
        id,
        titulo,
        valor,
        bairro,
        quartos,
        tipo
    FROM imoveis
    WHERE 1=1
    """

    parametros = []

    if bairro:
        query += " AND LOWER(bairro) LIKE LOWER(?)"
        parametros.append(f"%{bairro}%")

    if quartos > 0:
        query += " AND quartos >= ?"
        parametros.append(quartos)

    if tipo:
        query += " AND LOWER(tipo) = ?"
        parametros.append(tipo)

    query += " LIMIT 10"

    print("QUERY:", query)
    print("PARAMETROS:", parametros)

    cursor.execute(query, parametros)

    imoveis = cursor.fetchall()

    print("IMOVEIS ENCONTRADOS:", len(imoveis))

    conn.close()

    if not imoveis:
        return jsonify({
            "resultado": """
            <div style='padding:10px'>
                Nenhum imóvel encontrado com esses critérios.
            </div>
            """
        })

    resultado_html = ""

    for imovel in imoveis:

        resultado_html += f"""
        <div style="
            background:#0f172a;
            padding:12px;
            border-radius:8px;
            margin-top:8px;
            border-left:4px solid #f59e0b;
        ">
            <strong>{imovel['titulo']}</strong><br>

            🏠 {imovel['tipo']}<br>
            💰 {imovel['valor']}<br>
            📍 {imovel['bairro']}<br>
            🛏 {imovel['quartos']} quartos<br><br>

            <a href="/imovel/{imovel['id']}"
               style="
                    color:#f59e0b;
                    font-weight:bold;
                    text-decoration:none;
               ">
                ➔ Ver Detalhes
            </a>
        </div>
        """

    return jsonify({
        "resultado": resultado_html
    })



@app.route("/conectar_whatsapp")
def conectar_whatsapp():

    import requests

    usuario_id = session["usuario_id"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT whatsapp_sessao FROM usuarios WHERE id = ?",
        (usuario_id,)
    )

    usuario = cursor.fetchone()

    conn.close()

    r = requests.post(
        "https://zoom-leggings-viability.ngrok-free.dev/criar-sessao",
        json={
            "sessao": usuario["whatsapp_sessao"]
        }
    )

    print("RESPOSTA NODE:", r.text)

    return {
        "ok": True,
        "sessao": usuario["whatsapp_sessao"]
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


@app.route("/status_whatsapp")
@verificar_sessao
def status_whatsapp():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            whatsapp_status,
            whatsapp_numero
        FROM usuarios
        WHERE id = ?
    """, (session["usuario_id"],))

    usuario = cursor.fetchone()

    conn.close()

    return {
        "status": usuario["whatsapp_status"],
        "numero": usuario["whatsapp_numero"]
    }


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



@app.route("/atualizar_status_whatsapp", methods=["POST"])
def atualizar_status_whatsapp():

    dados = request.get_json()

    sessao = dados.get("sessao")
    status = dados.get("status")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET whatsapp_status = ?
        WHERE whatsapp_sessao = ?
    """, (status, sessao))

    conn.commit()
    conn.close()

    return {"sucesso": True}


@app.route("/teste_envio")
def teste_envio():

    requests.post(
        "https://zoom-leggings-viability.ngrok-free.dev/enviar",
        json={
            "sessao": "corretor_1",
            "numero": "5511920900085@c.us",
            "mensagem": "🚀 Teste SMARTZEN IMOB"
        }
    )

    return "Mensagem enviada"


@app.route("/superadmin/empresa/<int:empresa_id>/usuarios")
@super_admin_required
def gerenciar_usuarios_empresa(empresa_id):
    # Busca todos os usuários da empresa selecionada
    usuarios = db.execute("""
        SELECT id, nome, email, cargo, is_admin 
        FROM usuarios WHERE empresa_id = ?
    """, (empresa_id,)).fetchall()

    return render_template("gerenciar_usuarios.html", usuarios=usuarios, empresa_id=empresa_id)

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


@app.route('/site/<subdominio>')
def exibir_site(subdominio):
    conn = sqlite3.connect('/data/imobiliaria.db')
    conn.row_factory = sqlite3.Row # Para acessar colunas pelo nome
    cursor = conn.cursor()
    
    # 1. Busca as configurações da imobiliária
    empresa = cursor.execute("SELECT * FROM configuracoes_site WHERE subdominio = ?", (subdominio,)).fetchone()
    
    if not empresa:
        return "Site não encontrado", 404
        
    # 2. Busca todos os imóveis daquela empresa
    imoveis = cursor.execute("SELECT * FROM imoveis WHERE empresa_id = ?", (empresa['empresa_id'],)).fetchall()
    
    conn.close()
    
    # 3. Renderiza o template passando os dados
    return render_template('template_site.html', empresa=empresa, imoveis=imoveis)

@app.route("/cadastrar_imovel", methods=["GET", "POST"])
@verificar_sessao
def cadastrar_imovel():
    if request.method == "POST":

        empresa_id = session.get("empresa_id")
        user_id = session.get("usuario_id")

        valor = request.form.get("valor", "")

        valor = (
            valor.replace("R$", "")
                 .replace(".", "")
                 .replace(",", ".")
                 .strip()
        )

        try:
            valor = float(valor)
        except:
            valor = 0

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO imoveis (
                titulo, tipo, valor, cidade, bairro,
                quartos, banheiros, area, status, descricao,
                rua, iptu, condominio, link, cep,
                vaga_garagem, lazer, sacada, lavabo,
                usuario_id, empresa_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            user_id,
            empresa_id
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



# ==========================================
# 1. PÁGINA INICIAL / DASHBOARD
# ==========================================
@app.route("/")
@verificar_sessao
def index():
    # REMOVIDO: O redirecionamento automático que causava o loop
    # Agora o admin vê o dashboard da empresa dele normalmente
    
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Contagem segura por empresa_id
    cursor.execute("SELECT COUNT(*) FROM clientes WHERE empresa_id=?", (empresa_id,))
    total_clientes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM imoveis WHERE empresa_id=?", (empresa_id,))
    total_imoveis = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        total_clientes=total_clientes,
        total_imoveis=total_imoveis,
    )

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

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Só processa se for um envio de formulário
        email = request.form.get("email")
        senha = request.form.get("senha")

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        usuario = cursor.fetchone()

        if usuario and check_password_hash(usuario['senha'], senha):
            novo_token = secrets.token_hex(16)
            cursor.execute("UPDATE usuarios SET session_token = ? WHERE id = ?", 
                           (novo_token, usuario['id']))
            conn.commit()

            session["usuario_id"] = usuario['id']
            session["empresa_id"] = usuario['empresa_id']
            session["session_token"] = novo_token
            session["usuario_nome"] = usuario['nome']
            session["is_admin"] = usuario['is_admin']
            session["user_email"] = usuario['email']
            conn.close()
            return redirect('/')

        conn.close()
        return render_template("login.html", erro="E-mail ou senha incorretos.")
        return redirect("/login")

    # Se o método for GET, apenas mostra o HTML
    return render_template("login.html")



@app.route("/buscar_qr")
@verificar_sessao
def buscar_qr():

    usuario_id = session["usuario_id"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT whatsapp_sessao
        FROM usuarios
        WHERE id=?
    """, (usuario_id,))

    usuario = cursor.fetchone()

    conn.close()

    r = requests.get(
        f"https://zoom-leggings-viability.ngrok-free.dev/qr/{usuario['whatsapp_sessao']}"
    )

    return r.json()

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



@app.route("/whatsapp")
def whatsapp():

    if "usuario_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT whatsapp_sessao,
               whatsapp_status,
               whatsapp_numero
        FROM usuarios
        WHERE id = ?
    """, (session["usuario_id"],))

    usuario = cursor.fetchone()

    conn.close()

    return render_template(
        "whatsapp.html",
        sessao=usuario["whatsapp_sessao"],
        status=usuario["whatsapp_status"],
        numero=usuario["whatsapp_numero"]
    )


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
@verificar_sessao # Substituímos a verificação manual
def configuracoes():
    UPLOAD_FOLDER = app.config['UPLOAD_FOLDER_PERFIL'] # Usando a config global do app

    if request.method == "POST":
        file = request.files.get('foto')
        if file and file.filename != '':
            # Mantemos o nome fixo para evitar acúmulo de arquivos
            filename = f"usuario_{session['usuario_id']}.jpg"
            save_path = os.path.join(UPLOAD_FOLDER, filename)

            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)

            file.save(save_path)

            # Atualiza no banco
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            # Adicionamos a empresa_id aqui apenas por boa prática, embora 
            # o usuario_id já seja único no seu sistema
            cursor.execute("""
                UPDATE usuarios SET foto_url = ? 
                WHERE id = ? AND empresa_id = ?
            """, (f"uploads/perfil/{filename}", session["usuario_id"], session["empresa_id"]))
            conn.commit()
            conn.close()
            return redirect("/configuracoes")

    # Busca os dados atuais
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nome, foto_url FROM usuarios 
        WHERE id = ? AND empresa_id = ?
    """, (session["usuario_id"], session["empresa_id"]))
    usuario = cursor.fetchone()
    conn.close()

    return render_template("configuracoes.html", usuario=usuario)

# 3. PAINEL ADMINISTRATIVO (CONTROLE DO DONO)
# =========================================



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
        corretores = cursor.execute("SELECT id, nome, email, empresa_id, status_assinatura, validade_assinatura, is_admin FROM usuarios").fetchall()
        
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
    empresa_id = session.get('empresa_id')
    
    # CRÍTICO: Criptografe a senha antes de salvar
    senha_hash = generate_password_hash(senha_raw)
    
    conn = sqlite3.connect('/data/imobiliaria.db')
    cursor = conn.cursor()
    # Salve o senha_hash, não a senha_raw
    cursor.execute("INSERT INTO usuarios (email, senha, empresa_id) VALUES (?, ?, ?)", 
                   (email, senha_hash, empresa_id))
    conn.commit()
    conn.close()
    return "Usuário criado com sucesso!"



@app.route('/admin/novo-usuario')
def exibir_novo_usuario():
    # Verifica se a empresa está logada
    empresa_id = session.get('empresa_id')
    if not empresa_id:
        return "Acesso negado: você não está logado como empresa.", 403

    conn = sqlite3.connect('/data/imobiliaria.db')
    cursor = conn.cursor()
    
    # Filtra os usuários APENAS da empresa logada
    cursor.execute("SELECT id, email FROM usuarios WHERE empresa_id = ?", (empresa_id,))
    usuarios_db = cursor.fetchall()
    conn.close()
    
    lista_usuarios = [{"id": u[0], "email": u[1]} for u in usuarios_db]
    
    return render_template('novo-usuario.html', usuarios=lista_usuarios)


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
# 4. ROTAS DE CLIENTES
# ==========================================
@app.route("/clientes")
@verificar_sessao
def listar_clientes():
    empresa_id = session.get('empresa_id')

    conn = sqlite3.connect(DB_PATH) # Usei sua variável global DB_NAME
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM clientes WHERE empresa_id = ?", (empresa_id,))
    clientes = cursor.fetchall() # CORRIGIDO: Era conn.fetchall()
    conn.close()

    return render_template("clientes.html", clientes=clientes)

@app.route("/cadastrar_cliente", methods=["GET", "POST"])
@verificar_sessao  # Agora usamos o decorador de segurança que criamos
def cadastrar_cliente():
    if request.method == "POST":
        nome = request.form["nome"]
        telefone = request.form["telefone"]
        email = request.form["email"]
        interesse = request.form["interesse"]
        faixa_preco = request.form["faixa_preco"]
        bairro = request.form.get("bairro", "")
        sobre = request.form.get("sobre", "")
        entrada = request.form.get("entrada", "")
        pagamento = request.form.get("pagamento", "")

        # Recuperamos os IDs da sessão garantida pelo @verificar_sessao
        user_id = session["usuario_id"]
        empresa_id = session["empresa_id"]

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Inserimos os dados incluindo o campo empresa_id
        cursor.execute("""
            INSERT INTO clientes (nome, telefone, email, interesse, faixa_preco, bairro, sobre, entrada, pagamento, usuario_id, empresa_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nome, telefone, email, interesse, faixa_preco, bairro, sobre, entrada, pagamento, user_id, empresa_id))

        conn.commit()
        conn.close()
        return redirect("/clientes")

    return render_template("cadastrar_cliente.html")

# ==========================================
# 5. ROTAS DE IMÓVEIS
# ==========================================
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
    # O decorador @verificar_sessao já cuida da autenticação
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # A SEGURANÇA: Buscamos clientes filtrando pelo empresa_id
    cursor.execute("SELECT * FROM clientes WHERE empresa_id = ?", (empresa_id,))
    clientes = cursor.fetchall()
    conn.close()

    # Define suas etapas
    etapas = ["Novo Contato", "Visita Agendada", "Proposta Feita", "Negociação", "Fechado"]

    # Organiza os dados em um dicionário
    funil_dados = {etapa: [] for etapa in etapas}
    for c in clientes:
        status = c['status_funil'] or "Novo Contato"
        # Garante que o status exista nas etapas definidas
        if status in funil_dados:
            funil_dados[status].append(c)

    return render_template("funil.html", funil_dados=funil_dados, etapas=etapas)    

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
                lazer=?,
                vaga_garagem=?,
                sacada=?
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



@app.route('/Gerar_site')
def mostrar_gerador():
    return render_template('Gerar_site.html')
# ==========================================
# 6. INTELIGÊNCIA ARTIFICIAL / ANÚNCIOS
# ==========================================
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
@verificar_sessao # Substituímos a verificação manual pelo nosso decorador
def perfil_cliente(id):
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Busca dados do cliente filtrando pela empresa_id
    cursor.execute("""
        SELECT id, nome, telefone, email, interesse, faixa_preco, bairro, status_funil, cpf, endereco 
        FROM clientes WHERE id = ? AND empresa_id = ?
    """, (id, empresa_id))
    cliente = cursor.fetchone()

    if not cliente:
        conn.close()
        return "Cliente não encontrado ou não pertence a esta empresa.", 404

    # 2. Busca apenas os imóveis da MESMA empresa para o cálculo de match
    cursor.execute("""
        SELECT id, titulo, tipo, valor, cidade, bairro, foto 
        FROM imoveis WHERE empresa_id = ?
    """, (empresa_id,))
    imoveis = cursor.fetchall()
    conn.close()

    # Lógica de Match (mantida igual, mas agora usando dados isolados)
    matches_cliente = []
    c_interesse, c_faixa, c_bairro = cliente[4], cliente[5], cliente[6]
    c_bairro_txt = str(c_bairro).lower().strip() if c_bairro else ""
    interesse_txt = str(c_interesse).lower().strip() if c_interesse else ""

    for i in imoveis:
        i_id, i_titulo, i_valor, i_bairro, i_cidade, i_foto = i[0], i[1], i[3], i[5], i[4], i[6]
        i_bairro_txt = str(i_bairro).lower().strip() if i_bairro else ""

        porcentagem = 0
        if i_bairro_txt and (i_bairro_txt == c_bairro_txt or i_bairro_txt in interesse_txt): porcentagem += 50
        try:
            imovel_num = float(''.join(filter(str.isdigit, str(i_valor))))
            cliente_num = float(''.join(filter(str.isdigit, str(c_faixa))))
            if imovel_num <= (cliente_num * 1.10): porcentagem += 50
        except:
            if c_faixa and str(i_valor).strip() in str(c_faixa).strip(): porcentagem += 50

        if porcentagem >= 50:
            matches_cliente.append({"id": i_id, "titulo": i_titulo, "valor": i_valor, "local": f"{i_bairro}, {i_cidade}", "foto": i_foto, "porcentagem": porcentagem})

    return render_template("perfil_cliente.html", cliente=cliente, matches=matches_cliente)


@app.route("/cliente/atualizar_status/<int:id>", methods=["POST"])
@verificar_sessao
def atualizar_status_cliente(id):
    novo_status = request.form.get("status_funil")
    data_visita = request.form.get("data_visita")
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Corrigido de cliente_id para id (que é o argumento da função)
    cursor.execute("""
        UPDATE clientes 
        SET status_funil = ?, data_visita = ?
        WHERE id = ? AND empresa_id = ?
    """, (novo_status, data_visita, id, empresa_id)) 

    conn.commit()
    conn.close()

    return redirect(f"/cliente/{id}")


@app.route("/desconectar_whatsapp")
@verificar_sessao
def desconectar_whatsapp():

    import requests
    import sqlite3

    sessao = f"corretor_{session['usuario_id']}"

    requests.post(
        "https://zoom-leggings-viability.ngrok-free.dev/desconectar",
        json={
            "sessao": sessao
        }
    )

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET whatsapp_status='desconectado',
            whatsapp_numero=NULL
        WHERE id=?
    """, (session["usuario_id"],))

    conn.commit()
    conn.close()

    return redirect("/whatsapp")


@app.route("/cliente/atualizar_dados/<int:id>", methods=["POST"])
@verificar_sessao
def atualizar_dados_cliente(id):
    email = request.form.get("email")
    cpf = request.form.get("cpf") 
    endereco = request.form.get("endereco")
    telefone = request.form.get("telefone")
    empresa_id = session.get("empresa_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # CORREÇÃO: Removida a vírgula após endereco = ?
    cursor.execute("""
        UPDATE clientes 
        SET email = ?, cpf = ?, endereco = ?, telefone=?
        WHERE id = ? AND empresa_id = ?
    """, (email, cpf, endereco, telefone, id, empresa_id))

    conn.commit()
    conn.close()

    return redirect(f"/cliente/{id}")







if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

