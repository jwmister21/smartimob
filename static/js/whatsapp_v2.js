console.log("SMARTZEN WhatsApp V2 iniciado");


// =====================================
// ELEMENTOS
// =====================================


const statusText = document.querySelector(".status div:nth-child(2)");
const dot = document.querySelector(".dot");
const qrText = document.querySelector(".qr-text");




// =====================================
// LOG
// =====================================


function adicionarLog(texto){

    const logs = document.querySelector(".logs");


    const div = document.createElement("div");

    div.className="log";

    div.innerHTML =
    "["+ new Date().toLocaleTimeString() +"] "+texto;


    logs.appendChild(div);


    logs.scrollTop = logs.scrollHeight;

}




// =====================================
// STATUS
// =====================================


async function buscarStatus(){


try{


    const resposta =
    await fetch("/api/whatsapp/status");


    const dados =
    await resposta.json();



    if(dados.status === "connected"){


        statusText.innerHTML =
        "🟢 WhatsApp conectado";


        dot.style.background="#22c55e";


        qrText.innerHTML =
        "Conectado";


        adicionarLog(
        "Sessão ativa"
        );

    }



    else{


        statusText.innerHTML =
        "🟡 Aguardando conexão";


        dot.style.background="#f59e0b";

    }



}

catch(e){


    statusText.innerHTML =
    "🔴 Servidor offline";


    dot.style.background="#ef4444";


    adicionarLog(
    "Falha ao comunicar com servidor"
    );


}


}




// =====================================
// QR
// =====================================


async function buscarQR(){


adicionarLog(
"Solicitando novo QR Code..."
);


try{


const resposta =
await fetch("/api/whatsapp/qr");


const dados =
await resposta.json();



if(dados.qr){


qrText.innerHTML =
"QR Code carregado";


adicionarLog(
"QR atualizado"
);


}



}catch(e){


adicionarLog(
"Erro ao buscar QR"
);


}



}





// =====================================
// BOTÕES
// =====================================


document
.querySelector(".primary")
.addEventListener("click",buscarQR);





document
.querySelectorAll(".secondary")[0]
.addEventListener("click",()=>{


adicionarLog(
"Reconectando..."
);


buscarQR();


});





document
.querySelectorAll(".secondary")[1]
.addEventListener("click",async()=>{


adicionarLog(
"Desconectando..."
);



await fetch(
"/api/whatsapp/disconnect",
{
method:"POST"
}
);



});






// =====================================
// AUTO START
// =====================================


buscarStatus();


setInterval(
buscarStatus,
5000
);

