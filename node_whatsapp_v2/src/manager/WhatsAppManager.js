const {
    default: makeWASocket,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    DisconnectReason
} = require("@whiskeysockets/baileys");

const P = require("pino");
const QRCode = require("qrcode");
const fs = require("fs");
const path = require("path");

const config = require("../config");

class WhatsAppManager {

    constructor() {
        // 🔥 AGORA É MULTI-USER REAL
        // userId → sessaoId → socket
        this.sessoes = {};
    }

    // ================================
    // GET SESSÃO
    // ================================
    getSessao(userId, sessaoId) {
        return this.sessoes?.[userId]?.[sessaoId];
    }

    existeSessao(userId, sessaoId) {
        return !!this.getSessao(userId, sessaoId);
    }

    listarSessoes() {

        const lista = [];

        for (const userId in this.sessoes) {
            for (const sessaoId in this.sessoes[userId]) {

                const sessao = this.sessoes[userId][sessaoId];

                lista.push({
                    userId,
                    sessaoId,
                    status: sessao.status,
                    numero: sessao.numero,
                    nome: sessao.nome,
                    conectadoEm: sessao.conectadoEm
                });
            }
        }

        return lista;
    }

    // ================================
    // CONECTAR (MULTI USUÁRIO REAL)
    // ================================
    async conectar(userId, sessaoId) {

        if (!userId || !sessaoId) {
            throw new Error("Usuário ou sessão inválida.");
        }

        // cria estrutura
        if (!this.sessoes[userId]) {
            this.sessoes[userId] = {};
        }

        if (this.existeSessao(userId, sessaoId)) {
            return this.getSessao(userId, sessaoId);
        }

        const pastaSessao = path.join(
            config.SESSION_PATH,
            String(userId),
            String(sessaoId)
        );

        if (!fs.existsSync(pastaSessao)) {
            fs.mkdirSync(pastaSessao, { recursive: true });
        }

        const { state, saveCreds } =
            await useMultiFileAuthState(pastaSessao);

        const { version } =
            await fetchLatestBaileysVersion();

        const sock = makeWASocket({

            version,
            auth: state,
            logger: P({ level: config.LOG_LEVEL }),
            browser: config.BROWSER,
            printQRInTerminal: false

        });

        const sessao = {
            userId,
            sessaoId,
            sock,
            qr: null,
            status: "conectando",
            numero: null,
            nome: null,
            conectadoEm: null,
            ultimaAtividade: null
        };

        this.sessoes[userId][sessaoId] = sessao;

        // salvar credenciais
        sock.ev.on("creds.update", saveCreds);

        // eventos
        sock.ev.on("connection.update", async (update) => {

            const { connection, qr, lastDisconnect } = update;

            if (qr) {

                sessao.qr = await QRCode.toDataURL(qr);
                sessao.status = "qrcode";

                console.log(`[${userId} | ${sessaoId}] QR GERADO`);
            }

            if (connection === "open") {

                sessao.status = "conectado";
                sessao.qr = null;

                sessao.numero = sock.user?.id || null;
                sessao.nome = sock.user?.name || null;

                sessao.conectadoEm = new Date();
                sessao.ultimaAtividade = new Date();

                console.log(`[${userId} | ${sessaoId}] CONECTADO`);
            }

            if (connection === "close") {

                sessao.status = "desconectado";

                const codigo =
                    lastDisconnect?.error?.output?.statusCode;

                console.log(`[${userId} | ${sessaoId}] DESCONECTADO`);

                if (codigo !== DisconnectReason.loggedOut) {

                    console.log(`[${userId} | ${sessaoId}] RECONECTANDO...`);

                    delete this.sessoes[userId][sessaoId];

                    setTimeout(() => {
                        this.conectar(userId, sessaoId);
                    }, config.RECONNECT_DELAY);

                }
            }

        });

        return sessao;
    }

    // ================================
    // QR
    // ================================
    obterQR(userId, sessaoId) {
        const sessao = this.getSessao(userId, sessaoId);
        return sessao ? sessao.qr : null;
    }

    // ================================
    // STATUS
    // ================================
    obterStatus(userId, sessaoId) {
        const sessao = this.getSessao(userId, sessaoId);
        return sessao ? sessao.status : "desconectado";
    }

    // ================================
    // PERFIL
    // ================================
    obterPerfil(userId, sessaoId) {

        const sessao = this.getSessao(userId, sessaoId);

        if (!sessao) return null;

        return {
            numero: sessao.numero,
            nome: sessao.nome,
            conectadoEm: sessao.conectadoEm,
            status: sessao.status
        };
    }

    // ================================
    // ENVIO DE MENSAGEM
    // ================================
    async enviarMensagem(userId, sessaoId, numero, mensagem) {

        const sessao = this.getSessao(userId, sessaoId);

        if (!sessao || !sessao.sock) {
            throw new Error("Sessão não encontrada ou desconectada.");
        }

        const jid = numero.includes("@s.whatsapp.net")
            ? numero
            : `${numero}@s.whatsapp.net`;

        const result = await sessao.sock.sendMessage(jid, {
            text: mensagem
        });

        sessao.ultimaAtividade = new Date();

        return {
            sucesso: true,
            result
        };
    }
}

module.exports = new WhatsAppManager();
