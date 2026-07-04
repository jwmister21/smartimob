const {
    default: makeWASocket,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    DisconnectReason
} = require("@whiskeysockets/baileys");

const P = require("pino");
const QRCode = require("qrcode");
const path = require("path");
const fs = require("fs");

const SESSION_PATH = process.env.SESSION_PATH || path.join(__dirname, "sessions");

class WhatsAppManager {

    constructor() {
        this.sessoes = {};
    }

    async conectar(sessao) {

        if (this.sessoes[sessao]?.sock) {
            return;
        }

        const pastaSessao = path.join(SESSION_PATH, sessao);

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

            logger: P({
                level: "silent"
            }),

            browser: [
                "SMARTZEN IMOB",
                "Chrome",
                "1.0"
            ],

            printQRInTerminal: false

        });

        this.sessoes[sessao] = {

            sock,

            qr: null,

            status: "conectando",

            numero: null,

            conectadoEm: null

        };

        sock.ev.on("creds.update", saveCreds);

        sock.ev.on("connection.update", async (update) => {

            const {
                connection,
                lastDisconnect,
                qr
            } = update;

            if (qr) {

                this.sessoes[sessao].qr =
                    await QRCode.toDataURL(qr);

                this.sessoes[sessao].status =
                    "qrcode";

                console.log(`${sessao} -> QR GERADO`);

            }

            if (connection === "open") {

                this.sessoes[sessao].status =
                    "conectado";

                this.sessoes[sessao].qr = null;

                this.sessoes[sessao].numero =
                    sock.user?.id || null;

                this.sessoes[sessao].conectadoEm =
                    new Date();

                console.log(`${sessao} -> CONECTADO`);

            }

            if (connection === "close") {

                const codigo =
                    lastDisconnect?.error?.output?.statusCode;

                console.log(`${sessao} -> DESCONECTOU`);

                delete this.sessoes[sessao].sock;

                if (codigo !== DisconnectReason.loggedOut) {

                    console.log(`${sessao} -> RECONECTANDO`);

                    setTimeout(() => {

                        this.conectar(sessao);

                    }, 3000);

                } else {

                    this.sessoes[sessao].status =
                        "desconectado";

                }

            }

        });

    }

    obterQR(sessao) {

        return this.sessoes[sessao]?.qr || null;

    }

    obterStatus(sessao) {

        return this.sessoes[sessao]?.status || "desconectado";

    }

    obterNumero(sessao) {

        return this.sessoes[sessao]?.numero || null;

    }

    listarSessoes() {

        return this.sessoes;

    }

}

module.exports = new WhatsAppManager();
