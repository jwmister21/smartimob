const path = require("path");

const config = {

    // Porta do servidor
    PORT: process.env.PORT || 3001,

    // Pasta onde ficarão as sessões do WhatsApp
    SESSION_PATH: process.env.SESSION_PATH || path.join(__dirname, "..", "..", "sessions"),

    // Informações do navegador exibidas no WhatsApp
    BROWSER: [
        "SMARTZEN IMOB",
        "Chrome",
        "2.0"
    ],

    // Nome da API
    APP_NAME: "SMARTZEN WhatsApp",

    // Versão da API
    VERSION: "2.0.0",

    // Tempo para tentar reconectar (ms)
    RECONNECT_DELAY: 3000,

    // Log do Pino
    LOG_LEVEL: "silent"

};

module.exports = config;
