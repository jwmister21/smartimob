import os
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from google import genai
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from moviepy.video.VideoClip import ColorClip, TextClip, ImageClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy import concatenate_videoclips
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///imobiliaria.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.getenv('SECRET_KEY')

db = SQLAlchemy(app)

# --- MODELOS ---
class Empresa(db.Model):
    __tablename__ = "empresas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200))

class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200))
    email = db.Column(db.String(200), unique=True)
    senha = db.Column(db.Text)
    empresa_id = db.Column(db.Integer)
    status_assinatura = db.Column(db.String(50))
    session_token = db.Column(db.Text)
    foto_url = db.Column(db.Text)
    is_admin = db.Column(db.Integer, default=0)
    validade_assinatura = db.Column(db.String(20))

class Cliente(db.Model):
    __tablename__ = "clientes"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200))
    telefone = db.Column(db.String(50))
    email = db.Column(db.String(200))
    interesse = db.Column(db.Text)
    faixa_preco = db.Column(db.String(100))
    bairro = db.Column(db.String(100))
    status_funil = db.Column(db.String(100))
    data_visita = db.Column(db.String(20))
    empresa_id = db.Column(db.Integer)
    usuario_id = db.Column(db.Integer)
    cpf = db.Column(db.String(20))
    endereco = db.Column(db.Text)

class Imovel(db.Model):
    __tablename__ = "imoveis"
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200))
    tipo = db.Column(db.String(100))
    valor = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    bairro = db.Column(db.String(100))
    quartos = db.Column(db.Integer)
    banheiros = db.Column(db.Integer)
    area = db.Column(db.String(100))
    descricao = db.Column(db.Text)
    status = db.Column(db.String(50))
    empresa_id = db.Column(db.Integer)
    usuario_id = db.Column(db.Integer)

class FotoImovel(db.Model):
    __tablename__ = 'fotos_imoveis'
    id = db.Column(db.Integer, primary_key=True)
    imovel_id = db.Column(db.Integer, db.ForeignKey('imoveis.id'))
    nome_arquivo = db.Column(db.String(255))

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER_PERFIL'] = os.path.join(BASE_DIR, 'static', 'uploads', 'perfil')
app.config['UPLOAD_FOLDER_IMOVEIS'] = os.path.join(BASE_DIR, 'static', 'uploads', 'imoveis')

for pasta in [app.config['UPLOAD_FOLDER_PERFIL'], app.config['UPLOAD_FOLDER_IMOVEIS']]:
    os.makedirs(pasta, exist_ok=True)

client = genai.Client(api_key=os.getenv('GCP_API_KEY'))

# --- DECORATORS E SEGURANÇA ---
# --- 3. DECORATORS (CORRIGIDO) ---
def verificar_sessao(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Verifica se existe ID na sessão
        if "usuario_id" not in session:
            return redirect("/login")
        
        # 2. Busca o usuário no banco
        usuario = Usuario.query.get(session["usuario_id"])
        
        # 3. VALIDAÇÃO CRÍTICA:
        # Se o token da sessão for diferente do token salvo no banco, ele derruba
        if not usuario or usuario.session_token != session.get("session_token"):
            print("DEBUG: Token inválido ou usuário inexistente. Logout forçado.")
            session.clear()
            return redirect("/login")
            
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('is_admin') != 1: return "Acesso Negado.", 403
        return f(*args, **kwargs)
    return decorated_function

# --- ROTAS PRINCIPAIS ---
@app.route("/")
@verificar_sessao
def index():
    if session.get("is_admin") == 1: return redirect("/admin")
    empresa_id = session.get("empresa_id")
    return render_template("index.html", 
        total_clientes=Cliente.query.filter_by(empresa_id=empresa_id).count(),
        total_imoveis=Imovel.query.filter_by(empresa_id=empresa_id).count())

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")
        
        print(f"DEBUG: Tentativa de login para o email: {email}") # Isso aparecerá nos logs do terminal
        
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario:
            print(f"DEBUG: Usuário encontrado! Nome: {usuario.nome}")
            if check_password_hash(usuario.senha, senha):
                print("DEBUG: Senha correta!")
                # ... resto do código de sessão ...
                return redirect("/")
            else:
                print("DEBUG: Senha incorreta!")
        else:
            print("DEBUG: Usuário não encontrado no banco.")
            
        flash("E-mail ou senha incorretos.", "danger")
        return redirect("/login")
        
    return render_template("login.html")


@app.route("/cadastrar_usuario", methods=["GET", "POST"])
def cadastrar_usuario():
    if request.method == "POST":
        nova_empresa = Empresa(nome=request.form.get("nome_empresa") or "Sem Nome")
        db.session.add(nova_empresa)
        db.session.commit()
        novo_usuario = Usuario(nome=request.form.get("nome"), email=request.form.get("email"),
                               senha=generate_password_hash(request.form.get("senha")),
                               empresa_id=nova_empresa.id, status_assinatura="ativo")
        db.session.add(novo_usuario)
        db.session.commit()
        return redirect("/login")
    return render_template("cadastrar_usuario.html")

# --- ROTAS DE CLIENTES E IMÓVEIS (Incluindo /cliente/<int:id> e gerar_anuncio) ---

# ==========================================
# 4. ROTAS DE CLIENTES E IMÓVEIS
# ==========================================

@app.route("/clientes")
@verificar_sessao
def listar_clientes():
    empresa_id = session.get('empresa_id')
    clientes = Cliente.query.filter_by(empresa_id=empresa_id).all()
    return render_template("clientes.html", clientes=clientes)

@app.route("/cadastrar_cliente", methods=["GET", "POST"])
@verificar_sessao
def cadastrar_cliente():
    if request.method == "POST":
        novo_cliente = Cliente(
            nome=request.form["nome"],
            telefone=request.form["telefone"],
            email=request.form["email"],
            interesse=request.form["interesse"],
            faixa_preco=request.form["faixa_preco"],
            bairro=request.form.get("bairro", ""),
            usuario_id=session["usuario_id"],
            empresa_id=session["empresa_id"]
        )
        db.session.add(novo_cliente)
        db.session.commit()
        return redirect("/clientes")
    return render_template("cadastrar_cliente.html")

@app.route("/imoveis")
@verificar_sessao
def imoveis():
    empresa_id = session.get("empresa_id")
    lista_imoveis = Imovel.query.filter_by(empresa_id=empresa_id).all()
    return render_template("imoveis.html", imoveis=lista_imoveis)

@app.route("/imovel/<int:imovel_id>")
@verificar_sessao
def ver_imovel(imovel_id):
    empresa_id = session.get("empresa_id")
    imovel = Imovel.query.filter_by(id=imovel_id, empresa_id=empresa_id).first_or_404()
    return render_template("detalhes_imovel.html", imovel=imovel)

@app.route("/gerar_anuncio", methods=["GET", "POST"])
@verificar_sessao
def gerar_anuncio():
    empresa_id = session.get("empresa_id")
    lista_imoveis = Imovel.query.filter_by(empresa_id=empresa_id).all()
    anuncio, imovel_selecionado = None, None

    if request.method == "POST":
        id_imovel = request.form.get("imovel_id")
        imovel_selecionado = Imovel.query.filter_by(id=id_imovel, empresa_id=empresa_id).first()
        if imovel_selecionado:
            try:
                prompt = f"Crie um anúncio imobiliário persuasivo para: {imovel_selecionado.titulo} em {imovel_selecionado.bairro}. Valor: {imovel_selecionado.valor}. Descrição: {imovel_selecionado.descricao}"
                response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                anuncio = response.text
            except Exception as e:
                anuncio = f"Erro na IA: {e}"
                
    return render_template("gerar_anuncio.html", imoveis=lista_imoveis, anuncio=anuncio, imovel=imovel_selecionado)

@app.route("/cliente/<int:id>")
@verificar_sessao
def perfil_cliente(id):
    empresa_id = session.get("empresa_id")
    cliente = Cliente.query.filter_by(id=id, empresa_id=empresa_id).first_or_404()
    return render_template("perfil_cliente.html", cliente=cliente)

@app.route("/funil")
@verificar_sessao
def funil():
    empresa_id = session.get("empresa_id")
    clientes = Cliente.query.filter_by(empresa_id=empresa_id).all()
    etapas = ["Novo Contato", "Visita Agendada", "Proposta Feita", "Negociação", "Fechado"]
    funil_dados = {etapa: [c for c in clientes if (c.status_funil or "Novo Contato") == etapa] for etapa in etapas}
    return render_template("funil.html", funil_dados=funil_dados, etapas=etapas)
# --- INICIALIZAÇÃO ---
if __name__ == "__main__":
    with app.app_context(): db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
