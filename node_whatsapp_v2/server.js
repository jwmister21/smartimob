const express = require("express");
const cors = require("cors");

const app = express();

app.use(cors());
app.use(express.json());

// =========================
// ROTAS
// =========================
app.get("/", (req, res) => {
    res.json({
        sistema: "SMARTZEN WhatsApp",
        versao: "2.0.0",
        status: "online"
    });
});

// EXEMPLO API
app.post("/api/whatsapp/conectar", (req, res) => {
    return res.json({
        sucesso: true,
        mensagem: "ok conectar recebido",
        body: req.body
    });
});

// =========================
// PORTA RAILWAY (IMPORTANTE)
// =========================
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
    console.log("==================================");
    console.log("SMARTZEN WHATSAPP V2");
    console.log("PORTA:", PORT);
    console.log("==================================");
});
