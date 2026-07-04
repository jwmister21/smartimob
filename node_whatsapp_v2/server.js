const express = require("express");
const cors = require("cors");

const whatsapp = require("./whatsapp");

const app = express();

app.use(cors());
app.use(express.json());

const PORT = process.env.PORT || 3001;

// ================================
// HEALTH CHECK
// ================================
app.get("/", (req, res) => {

    res.json({
        sistema: "SMARTZEN WhatsApp",
        status: "online",
        versao: "2.0"
    });

});

// ================================
// CONECTAR
// ================================
app.post("/conectar", async (req, res) => {

    try {

        const { sessao } = req.body;

        if (!sessao) {

            return res.status(400).json({
                sucesso: false,
                erro: "Sessão não informada."
            });

        }

        await whatsapp.conectar(sessao);

        res.json({
            sucesso: true,
            mensagem: "Conectando..."
        });

    } catch (e) {

        console.error(e);

        res.status(500).json({
            sucesso: false,
            erro: e.message
        });

    }

});

// ================================
// QR CODE
// ================================
app.get("/qr/:sessao", (req, res) => {

    const qr = whatsapp.obterQR(req.params.sessao);

    res.json({
        qr
    });

});

// ================================
// STATUS
// ================================
app.get("/status/:sessao", (req, res) => {

    res.json({

        status: whatsapp.obterStatus(req.params.sessao),

        numero: whatsapp.obterNumero(req.params.sessao)

    });

});

// ================================
// LISTAR SESSÕES
// ================================
app.get("/sessoes", (req, res) => {

    const lista = {};

    const sessoes = whatsapp.listarSessoes();

    for (const nome in sessoes) {

        lista[nome] = {

            status: sessoes[nome].status,

            numero: sessoes[nome].numero

        };

    }

    res.json(lista);

});

// ================================

app.listen(PORT, () => {

    console.log("=========================================");
    console.log(" SMARTZEN WHATSAPP V2 ");
    console.log(" Porta:", PORT);
    console.log("=========================================");

});
