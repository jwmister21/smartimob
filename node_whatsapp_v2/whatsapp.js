const {
    makeWASocket,
    useMultiFileAuthState,
    DisconnectReason
} = require("@whiskeysockets/baileys");

const P = require("pino");
const QRCode = require("qrcode");
const fs = require("fs");
const path = require("path");

const sessoes = {};

// ==========================
// CONECTAR SESSÃO
// ==========================
async function conectarSessao(nomeSessao) {

    if (sessoes[nomeSessao]?.sock) {
        return;
    }

    const pastaSessao = path.join(__dirname, "sessions", nomeSessao);

    if (!fs.existsSync(pastaSessao)) {
        fs.mkdirSync(pastaSessao, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(pastaSessao);

    const sock = makeWASocket({

        auth: state,

        printQRInTerminal: false,

        logger: P({ level: "silent" })

    });

    sessoes[nomeSessao] = {

        sock,

        qr: null,

        status: "conectando"

    };

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {

        const { connection, qr, lastDisconnect } = update;

        if (qr) {

            sessoes[nomeSessao].qr = await QRCode.toDataURL(qr);

            sessoes[nomeSessao].status = "qrcode";

            console.log(`${nomeSessao} -> QR GERADO`);

        }

        if (connection === "open") {

            sessoes[nomeSessao].status = "conectado";

            sessoes[nomeSessao].qr = null;

            console.log(`${nomeSessao} -> CONECTADO`);

        }

        if (connection === "close") {

            const codigo =
                lastDisconnect?.error?.output?.statusCode;

            console.log(`${nomeSessao} -> DESCONECTOU`);

            delete sessoes[nomeSessao].sock;

            if (codigo !== DisconnectReason.loggedOut) {

                console.log(`${nomeSessao} -> RECONECTANDO...`);

                conectarSessao(nomeSessao);

            } else {

                sessoes[nomeSessao].status = "desconectado";

            }

        }

    });

}
// ==========================
// QR
// ==========================

function obterQR(nomeSessao) {

    return sessoes[nomeSessao]?.qr || null;

}

// ==========================
// STATUS
// ==========================

function obterStatus(nomeSessao) {

    return sessoes[nomeSessao]?.status || "desconectado";

}

// ==========================
// EXPORTA
// ==========================

module.exports = {

    conectarSessao,

    obterQR,

    obterStatus,

    sessoes

};
