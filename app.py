import os
import secrets
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
from moviepy.video.VideoClip import ImageClip
from moviepy import concatenate_videoclips
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///imobiliaria.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

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
    cargo = db.Column(db.String(100))
    is_admin = db.Column(db.Integer, default=0)

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
    empresa_id = db.Column(db.Integer)

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

app.secret_key = os.getenv('SECRET_KEY')

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER_PERFIL'] = os.path.join(BASE_DIR, 'static', 'uploads', 'perfil')
app.config['UPLOAD_FOLDER_IMOVEIS'] = os.path.join(BASE_DIR, 'static', 'uploads', 'imoveis')

for pasta in [app.config['UPLOAD_FOLDER_PERFIL'], app.config['UPLOAD_FOLDER_IMOVEIS']]:
    if not os.path.exists(pasta):
        os.makedirs(pasta)

# Nota: A partir daqui, usaremos db.session em vez de sqlite3
for pasta in [PATH_PERFIL, PATH_IMOVEIS]:
    if not os.path.exists(pasta):
        os.makedirs(pasta)

# Removido DB_NAME, o SQLAlchemy usa a variável de configuração do app

client = genai.Client(api_key=os.getenv('GCP_API_KEY'))

@app.context_processor
def injetar_lembretes():
    # Pega a data de hoje formatada como 'YYYY-MM-DD'
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    # Busca clientes onde a data_visita começa com a data de hoje
    # Certifique-se de que o campo data_visita existe no seu modelo Cliente
    lembretes = Cliente.query.filter(db.func.date(Cliente.data_visita) == hoje).all()
    
    return dict(lembretes=lembretes)

def verificar_sessao(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect("/login")
            
        # Verifica no banco se o token atual ainda é o mesmo
        usuario = Usuario.query.get(session["usuario_id"])
        
        # Se o token no banco for diferente do token da sessão, alguém logou em outro lugar
        if not usuario or usuario.session_token != session.get("session_token"):
            session.clear() # Desloga o usuário
            return redirect("/login")
            
        return f(*args, **kwargs)
    return decorated_function

# init_db() removido: o SQLAlchemy gerencia as tabelas automaticamente 
# através das classes de modelo que você definiu.


# --- ADMIN E GESTÃO (Substitui seu bloco de atualização e rotas admin) ---

# Nota: A função atualizar_banco() não é mais necessária. 
# Apenas certifique-se de que seus modelos (Usuario, Imovel, etc) 
# contenham todas as colunas que você deseja (foto_url, cpf, status, etc).

class FotoImovel(db.Model):
    __tablename__ = 'fotos_imoveis'
    id = db.Column(db.Integer, primary_key=True)
    imovel_id = db.Column(db.Integer, db.ForeignKey('imoveis.id'))
    nome_arquivo = db.Column(db.String(255))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('is_admin') != 1:
            return "Acesso Negado: Apenas administradores.", 403
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin/gestao")
@verificar_sessao
@admin_required
def tela_gestao():
    empresa_id = session.get('empresa_id')
    
    # Substituímos a query raw pela consulta ORM do SQLAlchemy
    # O resultado será uma lista de tuplas (usuario, total_imoveis)
    from sqlalchemy import func
    corretores_estatisticas = db.session.query(
        Usuario.nome, func.count(Imovel.id)
    ).outerjoin(Imovel, Usuario.id == Imovel.usuario_id).filter(
        Usuario.empresa_id == empresa_id
    ).group_by(Usuario.id).all()
    
    return render_template("gestao.html", corretores=corretores_estatisticas)

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
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



# --- ROTAS DE SUPER ADMIN E CONTROLE DE ASSINATURA ---

@app.route("/superadmin/usuario/editar/<int:user_id>", methods=["POST"])
@super_admin_required
def editar_usuario(user_id):
    dados = request.json
    usuario = Usuario.query.get_or_404(user_id)
    
    if 'nova_senha' in dados:
        usuario.senha = generate_password_hash(dados['nova_senha'])
    if 'ativo' in dados:
        usuario.status_assinatura = dados['ativo']
        
    db.session.commit()
    return jsonify({"status": "sucesso"})

@app.route("/superadmin/empresa/<int:empresa_id>/usuarios")
@super_admin_required
def gerenciar_usuarios_empresa(empresa_id):
    # Busca via ORM do SQLAlchemy
    usuarios = Usuario.query.filter_by(empresa_id=empresa_id).all()
    return render_template("gerenciar_usuarios.html", usuarios=usuarios, empresa_id=empresa_id)

@app.route("/superadmin/usuario/promover/<int:usuario_id>", methods=["POST"])
@super_admin_required
def tornar_admin(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    usuario.is_admin = 1
    db.session.commit()
    return jsonify({"status": "sucesso", "mensagem": "Usuário agora é Administrador!"})

# --- FUNÇÃO DE LOGIN (REESCRITA PARA SQLAlchemy) ---
def verificar_login():
    if "usuario_id" not in session: 
        return "redirect_login"
    
    usuario = Usuario.query.get(session["usuario_id"])
    
    if not usuario: 
        return "redirect_login"
    
    # Se for admin, passa direto
    if usuario.is_admin == 1: 
        return "ativo"
        
    if usuario.status_assinatura == "bloqueado": 
        return "bloqueado"
        
    if usuario.validade_assinatura:
        # Comparação de data segura
        validade = datetime.strptime(usuario.validade_assinatura, "%Y-%m-%d")
        if datetime.now() > validade: 
            return "vencido"
            
    return "ativo"
    # Busca os dados atuais garantindo o escopo da empresa
    # --- ROTA CONFIGURAÇÕES ---
@app.route("/configuracoes")
@verificar_sessao
def configuracoes():
    # Substituímos a query manual por ORM SQLAlchemy
    usuario = Usuario.query.filter_by(
        id=session["usuario_id"], 
        empresa_id=session["empresa_id"]
    ).first()
    
    # O template receberá o objeto 'usuario', permitindo usar usuario.nome, usuario.foto_url
    return render_template("configuracoes.html", usuario=usuario)

# --- ROTA RENDERIZAR VÍDEO ---
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
        # O ImageClip é carregado pelo MoviePy
        clip = ImageClip(caminho_foto).resized(height=720).with_duration(3)
        clips.append(clip)
    
    # 2. Junta os clips
    video = concatenate_videoclips(clips, method="compose")
    
    # 3. Adiciona o áudio
    caminho_audio = os.path.join('static', 'assets', 'musicas', 'fundo_imobiliaria.mp3')
    if os.path.exists(caminho_audio):
        audio_clip = AudioFileClip(caminho_audio).with_duration(video.duration)
        audio_clip = audio_clip.audio_fadein(1).audio_fadeout(1)
        video = video.with_audio(audio_clip)
    
    # 4. Renderiza o vídeo final
    nome_video = f"video_imovel_{imovel_id}.mp4"
    caminho_video = os.path.join(pasta_fotos, nome_video)
    
    video.write_videofile(caminho_video, codec="libx264", audio_codec="aac", fps=24)
    
    # 5. Limpa a memória
    video.close()
    
    return jsonify({
        "status": "sucesso", 
        "url_video": f"/static/uploads/imoveis/{nome_video}"
    })

# --- ROTA CADASTRAR IMOVEL ---
@app.route("/cadastrar_imovel", methods=["GET", "POST"])
@verificar_sessao
def cadastrar_imovel():
    if request.method == "POST":
        novo_imovel = Imovel(
            titulo=request.form.get("titulo"),
            tipo=request.form.get("tipo"),
            valor=request.form.get("valor"),
            cidade=request.form.get("cidade"),
            bairro=request.form.get("bairro"),
            quartos=request.form.get("quartos"),
            banheiros=request.form.get("banheiros"),
            area=request.form.get("area"),
            status=request.form.get("status"),
            descricao=request.form.get("descricao"),
            usuario_id=session.get("usuario_id"),
            empresa_id=session.get("empresa_id")
        )
        db.session.add(novo_imovel)
        db.session.commit() # O ID do imóvel é gerado agora
        
        # Processamento de fotos
        arquivos = request.files.getlist("fotos[]")
        for file in arquivos:
            if file and file.filename != "":
                nome_seguro = secure_filename(file.filename)
                nome_foto = f"{novo_imovel.id}_{int(datetime.now().timestamp())}_{nome_seguro}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER_IMOVEIS'], nome_foto))
                
                # Usando o modelo FotoImovel que definimos antes
                nova_foto = FotoImovel(imovel_id=novo_imovel.id, nome_arquivo=nome_foto)
                db.session.add(nova_foto)
        
        db.session.commit()
        return redirect("/imoveis")
        
    return render_template("cadastrar_imovel.html")

# --- FUNÇÃO DE LOGIN (SQLAlchemy) ---
def verificar_login():
    if "usuario_id" not in session:
        return "redirect_login"

    usuario = Usuario.query.get(session["usuario_id"])
    if not usuario:
        return "redirect_login"
        
    if usuario.is_admin == 1:
        return "ativo"

    if usuario.status_assinatura == "bloqueado":
        return "bloqueado"

    if usuario.validade_assinatura:
        data_vencimento = datetime.strptime(usuario.validade_assinatura, "%Y-%m-%d")
        if datetime.now() > data_vencimento:
            return "vencido"

    return "ativo"

# --- ROTA ATUALIZAR SENHA ---
@app.route("/atualizar_senha", methods=["POST"])
@verificar_sessao
def atualizar_senha():
    senha_atual = request.form.get("senha_atual")
    nova_senha = request.form.get("nova_senha")
    
    usuario = Usuario.query.get(session["usuario_id"])
    
    if check_password_hash(usuario.senha, senha_atual):
        usuario.senha = generate_password_hash(nova_senha)
        db.session.commit()
        flash("Senha atualizada com sucesso!", "success")
    else:
        flash("Senha atual incorreta.", "danger")
        
    return redirect("/configuracoes")


# ==========================================
# 1. PÁGINA INICIAL / DASHBOARD
# ==========================================
# --- ROTAS PRINCIPAIS: DASHBOARD, IA E LOGIN ---

@app.route("/")
@verificar_sessao
def index():
    if session.get("is_admin") == 1:
        return redirect("/admin")

    empresa_id = session.get("empresa_id")
    
    # Contagem via ORM SQLAlchemy
    total_clientes = Cliente.query.filter_by(empresa_id=empresa_id).count()
    total_imoveis = Imovel.query.filter_by(empresa_id=empresa_id).count()
    
    return render_template(
        "index.html",
        total_clientes=total_clientes,
        total_imoveis=total_imoveis,
    )

@app.route("/match_ia")
@verificar_sessao
def match_ia():
    if session.get("is_admin") == 1: 
        return redirect("/admin")

    empresa_id = session.get("empresa_id")
    
    # Busca via ORM
    clientes = Cliente.query.filter_by(empresa_id=empresa_id).all()
    imoveis = Imovel.query.filter_by(empresa_id=empresa_id).all()

    matches = []
    for c in clientes:
        # A lógica de match permanece igual, usando os atributos dos objetos
        c_bairro_txt = str(c.bairro).lower().strip() if c.bairro else ""
        interesse_txt = str(c.interesse).lower().strip() if c.interesse else ""
        
        for i in imoveis:
            i_bairro_txt = str(i.bairro).lower().strip() if i.bairro else ""
            
            porcentagem = 0
            if i_bairro_txt and (i_bairro_txt == c_bairro_txt or i_bairro_txt in interesse_txt):
                porcentagem += 50
                
            try:
                imovel_num = float(''.join(filter(str.isdigit, str(i.valor))))
                cliente_num = float(''.join(filter(str.isdigit, str(c.faixa_preco))))
                if imovel_num <= (cliente_num * 1.10):
                    porcentagem += 50
            except:
                if c.faixa_preco and str(i.valor).strip() in str(c.faixa_preco).strip():
                    porcentagem += 50

            if porcentagem >= 50:
                matches.append({
                    "cliente_nome": c.nome,
                    "cliente_telefone": c.telefone,
                    "imovel_id": i.id,
                    "imovel_titulo": i.titulo,
                    "imovel_foto": getattr(i, 'foto', 'sem_foto.jpg'), # Usando getattr caso não exista coluna foto
                    "imovel_valor": i.valor,
                    "imovel_local": f"{i.bairro}, {i.cidade}" if i.bairro else i.cidade,
                    "porcentagem": porcentagem
                })

    matches = sorted(matches, key=lambda x: x["porcentagem"], reverse=True)
    return render_template("match_ia.html", matches=matches)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")
        
        # Busca usuário via SQLAlchemy
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario and check_password_hash(usuario.senha, senha):
            novo_token = secrets.token_hex(16)
            usuario.session_token = novo_token
            db.session.commit()
            
            session["usuario_id"] = usuario.id
            session["empresa_id"] = usuario.empresa_id
            session["session_token"] = novo_token
            session["usuario_nome"] = usuario.nome
            session["is_admin"] = usuario.is_admin
            
            return redirect("/")
        
        flash("E-mail ou senha incorretos.", "danger")
        return redirect("/login")
        
    return render_template("login.html")

# --- CADASTRO, LOGOUT E CONFIGURAÇÕES ---

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

@app.route("/configuracoes", methods=["GET", "POST"])
@verificar_sessao
def configuracoes():
    UPLOAD_FOLDER = app.config['UPLOAD_FOLDER_PERFIL']
    
    usuario = Usuario.query.get(session["usuario_id"])
    
    if request.method == "POST":
        file = request.files.get('foto')
        if file and file.filename != '':
            filename = f"usuario_{usuario.id}.jpg"
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
            file.save(save_path)
            
            usuario.foto_url = f"uploads/perfil/{filename}"
            db.session.commit()
            return redirect("/configuracoes")

    return render_template("configuracoes.html", usuario=usuario)

# --- PAINEL ADMINISTRATIVO (SQLAlchemy) ---

@app.route("/admin")
@verificar_sessao
def admin():
    if session.get('is_admin') != 1:
        return "Acesso Negado.", 403

    # Métricas via ORM
    total_imoveis = Imovel.query.count()
    total_clientes = Cliente.query.count()
    
    # Lista de corretores
    corretores = Usuario.query.all()
    
    return render_template(
        "admin.html", 
        corretores=corretores, 
        total_imoveis=total_imoveis, 
        total_clientes=total_clientes
    )

# Rota para processar as ações (Promover, Bloquear, Resetar Senha)
# --- ROTAS DE ADMINISTRAÇÃO E GESTÃO DE CONTAS ---

@app.route("/admin/acao/<int:user_id>", methods=["POST"])
@verificar_sessao
def admin_acao(user_id):
    if session.get('is_admin') != 1:
        return "Acesso Negado.", 403
        
    acao = request.form.get('acao')
    usuario = Usuario.query.get_or_404(user_id)
    
    if acao == 'promover_admin':
        usuario.is_admin = 1
    elif acao == 'bloquear':
        usuario.status_assinatura = 'bloqueado'
    elif acao == 'ativar':
        usuario.status_assinatura = 'ativo'
    elif acao == 'resetar_senha':
        nova_senha = request.form.get('nova_senha')
        usuario.senha = generate_password_hash(nova_senha)
        
    db.session.commit()
    return redirect(url_for('admin'))

@app.route("/admin/bloquear/<int:id>")
@verificar_sessao
def admin_bloquear(id):
    if session.get("is_admin") != 1:
        return "Negado", 403
    
    usuario = Usuario.query.get_or_404(id)
    usuario.status_assinatura = 'bloqueado'
    db.session.commit()
    return redirect("/admin")

@app.route("/admin/liberar/<int:id>", methods=["POST"])
@verificar_sessao
def admin_liberar(id):
    if session.get("is_admin") != 1:
        return "Negado", 403
        
    usuario = Usuario.query.get_or_404(id)
    usuario.status_assinatura = 'ativo'
    usuario.validade_assinatura = request.form["validade"]
    
    db.session.commit()
    return redirect("/admin")

@app.route("/admin/resetar_senha/<int:id>", methods=["POST"])
@verificar_sessao
def admin_resetar_senha(id):
    if session.get("is_admin") != 1:
        return "Acesso negado", 403
        
    usuario = Usuario.query.get_or_404(id)
    usuario.senha = generate_password_hash(request.form["nova_senha"])
    
    db.session.commit()
    flash("Senha alterada com sucesso!", "success")
    return redirect("/admin")

# ==========================================
# 4. ROTAS DE CLIENTES
# ==========================================
# --- ROTAS DE CLIENTES E IMÓVEIS (SQLAlchemy) ---

@app.route("/clientes")
@verificar_sessao
def listar_clientes():
    empresa_id = session.get('empresa_id')
    # Busca todos os clientes da empresa
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
    # Busca imóveis com as fotos relacionadas (se você definiu o relationship no modelo)
    lista_imoveis = Imovel.query.filter_by(empresa_id=empresa_id).all()
    
    # O SQLAlchemy permite acessar fotos_imoveis diretamente se estiver mapeado
    return render_template("imoveis.html", imoveis=lista_imoveis)

@app.route("/excluir_imovel/<int:id>")
@verificar_sessao
def excluir_imovel(id):
    empresa_id = session.get("empresa_id")
    
    # Busca o imóvel garantindo que ele pertença à empresa do usuário
    imovel = Imovel.query.filter_by(id=id, empresa_id=empresa_id).first_or_404()
    
    # Remove arquivo físico se existir
    if imovel.foto:
        caminho_foto = os.path.join(app.config['UPLOAD_FOLDER_IMOVEIS'], imovel.foto)
        if os.path.exists(caminho_foto):
            os.remove(caminho_foto)
    
    # Remove também as fotos da tabela relacionada
    FotoImovel.query.filter_by(imovel_id=id).delete()
    
    # Remove o imóvel e commita
    db.session.delete(imovel)
    db.session.commit()
    
    flash("Imóvel excluído com sucesso!", "success")
    return redirect("/imoveis")
# --- ROTA DE DETALHES UNIFICADA (Substitua as antigas por esta) ---
# --- ROTAS DE DETALHES, FUNIL E EDIÇÃO (SQLAlchemy) ---

@app.route("/imovel/<int:imovel_id>")
@verificar_sessao
def ver_imovel(imovel_id):
    empresa_id = session.get("empresa_id")
    
    # Busca o imóvel garantindo o isolamento da empresa
    imovel = Imovel.query.filter_by(id=imovel_id, empresa_id=empresa_id).first_or_404(description="Imóvel não encontrado ou sem permissão.")
    
    # O SQLAlchemy carrega as fotos automaticamente se o relacionamento existir
    return render_template("detalhes_imovel.html", imovel=imovel)

@app.route("/funil")
@verificar_sessao
def funil():
    empresa_id = session.get("empresa_id")
    clientes = Cliente.query.filter_by(empresa_id=empresa_id).all()
    
    etapas = ["Novo Contato", "Visita Agendada", "Proposta Feita", "Negociação", "Fechado"]
    
    # Organiza os dados em um dicionário
    funil_dados = {etapa: [] for etapa in etapas}
    for c in clientes:
        status = c.status_funil or "Novo Contato"
        if status in funil_dados:
            funil_dados[status].append(c)
            
    return render_template("funil.html", funil_dados=funil_dados, etapas=etapas)

@app.route("/editar_imovel/<int:id>", methods=["GET", "POST"])
@verificar_sessao
def editar_imovel(id):
    empresa_id = session.get("empresa_id")
    imovel = Imovel.query.filter_by(id=id, empresa_id=empresa_id).first_or_404()
    
    if request.method == "POST":
        imovel.titulo = request.form["titulo"]
        imovel.tipo = request.form["tipo"]
        imovel.valor = request.form["valor"]
        imovel.cidade = request.form["cidade"]
        imovel.bairro = request.form["bairro"]
        imovel.quartos = request.form["quartos"]
        imovel.banheiros = request.form["banheiros"]
        imovel.area = request.form["area"]
        imovel.status = request.form["status"]
        imovel.descricao = request.form["descricao"]
        
        db.session.commit()
        return redirect("/imoveis")
    
    return render_template("editar_imovel.html", imovel=imovel)# ==========================================
# 6. INTELIGÊNCIA ARTIFICIAL / ANÚNCIOS
# ==========================================
# --- ROTAS DE ANÚNCIOS, PERFIL DE CLIENTE E ATUALIZAÇÕES ---

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
            localizacao = f"{imovel_selecionado.bairro}, {imovel_selecionado.cidade}"

            try:
                prompt = f"""
Você é um especialista em marketing imobiliário. Crie um anúncio persuasivo para:
- Tipo: {imovel_selecionado.tipo}
- Localização: {localizacao}
- Valor: {imovel_selecionado.valor}
- Descrição técnica: {imovel_selecionado.descricao}

Siga estas diretrizes: 
1. Headline impactante.
2. Descrição atraente do estilo de vida.
3. Diferenciais em tópicos.
4. Chamada para ação final.
"""
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt
                )
                anuncio = response.text
            except Exception as e:
                anuncio = f"Erro ao conectar com a IA: {e}"
                
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
    cliente = Cliente.query.filter_by(id=id, empresa_id=empresa_id).first_or_404()
    imoveis = Imovel.query.filter_by(empresa_id=empresa_id).all()

    matches_cliente = []
    c_bairro_txt = str(cliente.bairro).lower().strip() if cliente.bairro else ""
    interesse_txt = str(cliente.interesse).lower().strip() if cliente.interesse else ""

    for i in imoveis:
        i_bairro_txt = str(i.bairro).lower().strip() if i.bairro else ""
        porcentagem = 0
        
        if i_bairro_txt and (i_bairro_txt == c_bairro_txt or i_bairro_txt in interesse_txt): 
            porcentagem += 50
        try:
            imovel_num = float(''.join(filter(str.isdigit, str(i.valor))))
            cliente_num = float(''.join(filter(str.isdigit, str(cliente.faixa_preco))))
            if imovel_num <= (cliente_num * 1.10): porcentagem += 50
        except:
            if cliente.faixa_preco and str(i.valor).strip() in str(cliente.faixa_preco).strip():
                porcentagem += 50

        if porcentagem >= 50:
            matches_cliente.append({
                "id": i.id, "titulo": i.titulo, "valor": i.valor, 
                "local": f"{i.bairro}, {i.cidade}", "foto": getattr(i, 'foto', ''), 
                "porcentagem": porcentagem
            })

    return render_template("perfil_cliente.html", cliente=cliente, matches=matches_cliente)

@app.route("/cliente/atualizar_status/<int:id>", methods=["POST"])
@verificar_sessao
def atualizar_status_cliente(id):
    cliente = Cliente.query.filter_by(id=id, empresa_id=session.get("empresa_id")).first_or_404()
    cliente.status_funil = request.form.get("status_funil")
    cliente.data_visita = request.form.get("data_visita")
    db.session.commit()
    return redirect(f"/cliente/{id}")

@app.route("/cliente/atualizar_dados/<int:id>", methods=["POST"])
@verificar_sessao
def atualizar_dados_cliente(id):
    cliente = Cliente.query.filter_by(id=id, empresa_id=session.get("empresa_id")).first_or_404()
    cliente.email = request.form.get("email")
    cliente.cpf = request.form.get("cpf")
    cliente.endereco = request.form.get("endereco")
    db.session.commit()
    return redirect(f"/cliente/{id}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)# --- ROTAS DE ANÚNCIOS, PERFIL DE CLIENTE E ATUALIZAÇÕES ---

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
            localizacao = f"{imovel_selecionado.bairro}, {imovel_selecionado.cidade}"

            try:
                prompt = f"""
Você é um especialista em marketing imobiliário. Crie um anúncio persuasivo para:
- Tipo: {imovel_selecionado.tipo}
- Localização: {localizacao}
- Valor: {imovel_selecionado.valor}
- Descrição técnica: {imovel_selecionado.descricao}

Siga estas diretrizes: 
1. Headline impactante.
2. Descrição atraente do estilo de vida.
3. Diferenciais em tópicos.
4. Chamada para ação final.
"""
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt
                )
                anuncio = response.text
            except Exception as e:
                anuncio = f"Erro ao conectar com a IA: {e}"
                
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
    cliente = Cliente.query.filter_by(id=id, empresa_id=empresa_id).first_or_404()
    imoveis = Imovel.query.filter_by(empresa_id=empresa_id).all()

    matches_cliente = []
    c_bairro_txt = str(cliente.bairro).lower().strip() if cliente.bairro else ""
    interesse_txt = str(cliente.interesse).lower().strip() if cliente.interesse else ""

    for i in imoveis:
        i_bairro_txt = str(i.bairro).lower().strip() if i.bairro else ""
        porcentagem = 0
        
        if i_bairro_txt and (i_bairro_txt == c_bairro_txt or i_bairro_txt in interesse_txt): 
            porcentagem += 50
        try:
            imovel_num = float(''.join(filter(str.isdigit, str(i.valor))))
            cliente_num = float(''.join(filter(str.isdigit, str(cliente.faixa_preco))))
            if imovel_num <= (cliente_num * 1.10): porcentagem += 50
        except:
            if cliente.faixa_preco and str(i.valor).strip() in str(cliente.faixa_preco).strip():
                porcentagem += 50

        if porcentagem >= 50:
            matches_cliente.append({
                "id": i.id, "titulo": i.titulo, "valor": i.valor, 
                "local": f"{i.bairro}, {i.cidade}", "foto": getattr(i, 'foto', ''), 
                "porcentagem": porcentagem
            })

    return render_template("perfil_cliente.html", cliente=cliente, matches=matches_cliente)

@app.route("/cliente/atualizar_status/<int:id>", methods=["POST"])
@verificar_sessao
def atualizar_status_cliente(id):
    cliente = Cliente.query.filter_by(id=id, empresa_id=session.get("empresa_id")).first_or_404()
    cliente.status_funil = request.form.get("status_funil")
    cliente.data_visita = request.form.get("data_visita")
    db.session.commit()
    return redirect(f"/cliente/{id}")

@app.route("/cliente/atualizar_dados/<int:id>", methods=["POST"])
@verificar_sessao
def atualizar_dados_cliente(id):
    cliente = Cliente.query.filter_by(id=id, empresa_id=session.get("empresa_id")).first_or_404()
    cliente.email = request.form.get("email")
    cliente.cpf = request.form.get("cpf")
    cliente.endereco = request.form.get("endereco")
    db.session.commit()
    return redirect(f"/cliente/{id}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
