const express = require("express");
const cors = require("cors");
const wppconnect = require("@wppconnect-team/wppconnect");


const app = express();


app.use(cors());
app.use(express.json());



let clientes = {};

let qrs = {};

let statusUsuarios = {};





async function iniciarWhatsApp(session){


    if(clientes[session]){

        return;

    }



    console.log(
    "Iniciando:",
    session
    );




    const client = await wppconnect.create({


        session:session,


        folderNameToken:"tokens",


        autoClose:0,



        puppeteerOptions:{


            executablePath:"/usr/bin/chromium",


            args:[

            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage"

            ]

        },




        catchQR:(qr)=>{


            console.log(
            "QR RECEBIDO",
            session
            );


            qrs[session]=qr;


            statusUsuarios[session]="waiting";


        },




        statusFind:(status)=>{


            console.log(
            session,
            status
            );



            if(
            status==="isLogged" ||
            status==="inChat" ||
            status==="qrReadSuccess"
            ){


                statusUsuarios[session]="connected";


            }


            if(
            status==="disconnectedMobile"
            ){


                statusUsuarios[session]="disconnected";


            }



        }


    });



    clientes[session]=client;



    try{


        const conectado =
        await client.isConnected();



        if(conectado){


            statusUsuarios[session]="connected";


        }


    }catch(e){}



}








// iniciar sessão

app.post("/start",
async(req,res)=>{


    const session =
    req.body.session_name;



    if(!session){

        return res.json({

            error:"session_name obrigatório"

        });

    }



    await iniciarWhatsApp(session);



    res.json({

        success:true,

        session:session

    });



});








// status

app.get(
"/status/:session",
(req,res)=>{


const session =
req.params.session;



res.json({


status:
statusUsuarios[session]
||
"disconnected"


});


});








// qr

app.get(
"/qr/:session",
(req,res)=>{


const session =
req.params.session;



res.json({


qr:
qrs[session]
||
null,


status:
statusUsuarios[session]
||
"disconnected"


});


});









// desconectar

app.post(
"/disconnect/:session",
async(req,res)=>{


const session =
req.params.session;



if(clientes[session]){


await clientes[session].logout();


delete clientes[session];


}



statusUsuarios[session]="disconnected";


res.json({

success:true

});


});









app.listen(
3001,
()=>{


console.log(
"WhatsApp Multiuser rodando porta 3001"
);


});
