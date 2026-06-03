import os
import secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from sqlalchemy import func

# --- 1. CONFIGURAÇÕES ---
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///imobiliaria.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.getenv('SECRET_KEY')

db = SQLAlchemy(app)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER_PERFIL'] = os.path.join(BASE_DIR, 'static', 'uploads', 'perfil')
app.config['UPLOAD_FOLDER_IMOVEIS'] = os.path.join(BASE_DIR, 'static', 'uploads', 'imoveis')

for pasta in [app.config['UPLOAD_FOLDER_PERFIL'], app.config['UPLOAD_FOLDER_IMOVEIS']]:
    os.makedirs(pasta, exist_ok=True)

client = genai.Client(api_key=os.getenv('GCP_API_KEY'))

# --- 2. MODELOS ---
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
    empresa_id = db.Column(db.Integer)
    usuario_id = db.Column(db.Integer)

# --- 3. DECORATORS ---
def verificar_sessao(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session: return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# --- 4. ROTAS (Principais) ---
@app.route("/")
@verificar_sessao
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and check_password_hash(usuario.senha, senha):
            session["usuario_id"] = usuario.id
            session["empresa_id"] = usuario.empresa_id
            return redirect("/")
        flash("Erro no login", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/cadastrar_usuario", methods=["GET", "POST"])
def cadastrar_usuario():
    if request.method == "POST":
        nome = request.form.get("nome")
        email = request.form.get("email")
        senha_pura = request.form.get("senha")
        nome_empresa = request.form.get("nome_empresa") or "Sem Nome"
        
        try:
            # 1. Cria a empresa
            nova_empresa = Empresa(nome=nome_empresa)
            db.session.add(nova_empresa)
            db.session.commit() # Commita para gerar o ID da empresa
            
            # 2. Cria o usuário vinculado à empresa
            novo_usuario = Usuario(
                nome=nome,
                email=email,
                senha=generate_password_hash(senha_pura),
                empresa_id=nova_empresa.id,
                status_assinatura="ativo"
            )
            db.session.add(novo_usuario)
            db.session.commit()
            
            flash("Conta criada com sucesso! Faça login.", "success")
            return redirect("/login")
        except Exception as e:
            db.session.rollback()
            flash("Erro ao cadastrar. Tente novamente.", "danger")
            return redirect("/cadastrar_usuario")
            
    return render_template("cadastrar_usuario.html")

# --- 5. INICIALIZAÇÃO ---
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
