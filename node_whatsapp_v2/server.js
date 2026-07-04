const express = require("express");
const cors = require("cors");

const config = require("./src/config");
const whatsappRoutes = require("./src/routes/whatsapp");

const app = express();

// ==============================
// MIDDLEWARES
// ==============================

app.use(cors());

app.use(express.json({
    limit: "50mb"
}));

app.use(express.urlencoded({
    extended: true,
    limit: "50mb"
}));

// ==============================
// ROTA PRINCIPAL
// ==============================

app.get("/", (req, res) => {

    res.json({

        sistema: config.APP_NAME,

        versao: config.VERSION,

        status: "online"

    });

});

// ==============================
// ROTAS WHATSAPP
// ==============================

app.use("/api/whatsapp", whatsappRoutes);

// ==============================
// ROTA NÃO ENCONTRADA
// ==============================

app.use((req, res) => {

    res.status(404).json({

        sucesso: false,

        erro: "Rota não encontrada."

    });

});

// ==============================
// TRATAMENTO DE ERROS
// ==============================

app.use((err, req, res, next) => {

    console.error(err);

    res.status(500).json({

        sucesso: false,

        erro: err.message

    });

});

// ==============================
// START SERVER
// ==============================

app.listen(config.PORT, () => {

    console.log("==========================================");

    console.log(" SMARTZEN WHATSAPP ");

    console.log(" Porta:", config.PORT);

    console.log(" Versão:", config.VERSION);

    console.log("==========================================");

});
