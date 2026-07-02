const express = require("express");
const cors = require("cors");
const wppconnect = require("@wppconnect-team/wppconnect");


const app = express();


app.use(cors());

app.use(express.json());



let client = null;

let qrCode = null;

let status = "disconnected";





wppconnect.create({

    session:"smartzen",

    catchQR:(base64Qr)=>{

        console.log("QR RECEBIDO");

        qrCode = base64Qr;

        status="waiting";

    },


    statusFind:(statusSession)=>{

        console.log(
        "STATUS:",
        statusSession
        );


        if(
        statusSession==="isLogged"
        ){

            status="connected";

        }


    }


})
.then((c)=>{


client=c;


});






app.get(
"/status",
(req,res)=>{


res.json({

status:status

});


});






app.get(
"/qr",
(req,res)=>{


res.json({

qr:qrCode,

status:status

});


});







app.post(
"/disconnect",
async(req,res)=>{


if(client){

await client.logout();

}


status="disconnected";


res.json({

success:true

});


});







app.listen(
3001,
()=>{

console.log(
"WhatsApp V2 rodando porta 3001"
);

});
