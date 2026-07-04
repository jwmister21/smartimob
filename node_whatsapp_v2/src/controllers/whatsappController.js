const whatsapp = require("../manager/WhatsAppManager");

// ================================
// CONECTAR
// ================================
exports.conectar = async (req, res) => {

    try {

        const { sessao } = req.body;

        if (!sessao) {

            return res.status(400).json({
                sucesso: false,
                erro: "Sessão não informada."
            });

        }

        await whatsapp.conectar(sessao);

        return res.json({

            sucesso: true,

            mensagem: "Conectando...",

            sessao

        });

    } catch (erro) {

        console.error(erro);

        return res.status(500).json({

            sucesso: false,

            erro: erro.message

        });

    }

};

// ================================
// QR CODE
// ================================
exports.qr = (req, res) => {

    const { sessao } = req.params;

    return res.json({

        sucesso: true,

        qr: whatsapp.obterQR(sessao)

    });

};

// ================================
// STATUS
// ================================
exports.status = (req, res) => {

    const { sessao } = req.params;

    return res.json({

        sucesso: true,

        status: whatsapp.obterStatus(sessao)

    });

};

// ================================
// PERFIL
// ================================
exports.perfil = (req, res) => {

    const { sessao } = req.params;

    return res.json({

        sucesso: true,

        perfil: whatsapp.obterPerfil(sessao)

    });

};

// ================================
// LISTAR SESSÕES
// ================================
exports.sessoes = (req, res) => {

    return res.json({

        sucesso: true,

        sessoes: whatsapp.listarSessoes()

    });

};
