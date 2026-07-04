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

        this.sessoes = new Map();

    }

    getSessao(id) {

        return this.sessoes.get(id);

    }

    existeSessao(id) {

        return this.sessoes.has(id);

    }

    listarSessoes() {

        const lista = [];

        for (const [id, sessao] of this.sessoes.entries()) {

            lista.push({

                id,

                status: sessao.status,

                numero: sessao.numero,

                nome: sessao.nome,

                conectadoEm: sessao.conectadoEm

            });

        }

        return lista;

    }

    async conectar(id) {

        if (!id) {

            throw new Error("Sessão inválida.");

        }

        if (this.existeSessao(id)) {

            return this.getSessao(id);

        }

        const pastaSessao = path.join(
            config.SESSION_PATH,
            id
        );

        if (!fs.existsSync(pastaSessao)) {

            fs.mkdirSync(
                pastaSessao,
                { recursive: true }
            );

        }

        const {
            state,
            saveCreds
        } = await useMultiFileAuthState(
            pastaSessao
        );

        const {
            version
        } = await fetchLatestBaileysVersion();

        const sock = makeWASocket({

            version,

            auth: state,

            logger: P({

                level: config.LOG_LEVEL

            }),

            browser: config.BROWSER,

            printQRInTerminal: false

        });

        const sessao = {

            id,

            sock,

            qr: null,

            status: "conectando",

            numero: null,

            nome: null,

            conectadoEm: null,

            ultimaAtividade: null

        };

        this.sessoes.set(id, sessao);

        sock.ev.on(
            "creds.update",
            saveCreds
        );

        sock.ev.on(
            "connection.update",
            async (update) => {

                const {

                    connection,

                    qr,

                    lastDisconnect

                } = update;

                if (qr) {

                    sessao.qr = await QRCode.toDataURL(qr);

                    sessao.status = "qrcode";

                    console.log(`[${id}] QR GERADO`);

                }

                if (connection === "open") {

                    sessao.status = "conectado";

                    sessao.qr = null;

                    sessao.numero = sock.user?.id || null;

                    sessao.nome = sock.user?.name || null;

                    sessao.conectadoEm = new Date();

                    sessao.ultimaAtividade = new Date();

                    console.log(`[${id}] CONECTADO`);

                }

                if (connection === "close") {

                    sessao.status = "desconectado";

                    const codigo =
                        lastDisconnect?.error?.output?.statusCode;

                    console.log(`[${id}] DESCONECTADO`);

                    if (codigo !== DisconnectReason.loggedOut) {

                        console.log(`[${id}] RECONECTANDO...`);

                        this.sessoes.delete(id);

                        setTimeout(() => {

                            this.conectar(id);

                        }, config.RECONNECT_DELAY);

                    }

                }

            }
        );

        return sessao;

    }

    obterQR(id) {

        const sessao = this.getSessao(id);

        if (!sessao) {

            return null;

        }

        return sessao.qr;

    }

    obterStatus(id) {

        const sessao = this.getSessao(id);

        if (!sessao) {

            return "desconectado";

        }

        return sessao.status;

    }

    obterPerfil(id) {

        const sessao = this.getSessao(id);

        if (!sessao) {

            return null;

        }

        return {

            numero: sessao.numero,

            nome: sessao.nome,

            conectadoEm: sessao.conectadoEm,

            status: sessao.status

        };

    }

}

module.exports = new WhatsAppManager();
