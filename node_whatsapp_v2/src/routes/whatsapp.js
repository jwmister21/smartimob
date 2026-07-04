const express = require("express");

const router = express.Router();

const controller = require("../controllers/whatsappController");

// ===============================
// CONECTAR
// ===============================
router.post(
    "/conectar",
    controller.conectar
);

// ===============================
// QR CODE
// ===============================
router.get(
    "/qr/:sessao",
    controller.qr
);

// ===============================
// STATUS
// ===============================
router.get(
    "/status/:sessao",
    controller.status
);

// ===============================
// PERFIL
// ===============================
router.get(
    "/perfil/:sessao",
    controller.perfil
);

// ===============================
// LISTAR SESSÕES
// ===============================
router.get(
    "/sessoes",
    controller.sessoes
);

module.exports = router;
