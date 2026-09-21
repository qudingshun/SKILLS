/**
 * 提取重点邮件中的订单数据，以表格形式输出
 */
const net = require('net');
const { simpleParser } = require('mailparser');
const iconv = require('iconv-lite');

const CFG = {user:'dingshun_qu@whirlpool-china.com',pass:process.env.MAIL_PASS||'',host:'imap.qiye.163.com',port:143};

const EMAILS = [
  [9821, 'INBOX'],      // 澳洲Kogan
  [2450, '&WRaNOFbilh8-'], // 台湾8月新订单
  [2452, '&WRaNOFbilh8-'], // 拉美洗衣机
  [2453, '&WRaNOFbilh8-'], // 大连万博配件
];

let tag=0,pending={},buf='',responses=[],litRem=0,litD='',inLit=false;
const sock=net.connect(CFG.port,CFG.host);
sock.on('data',(d)=>{buf+=d.toString();
while(buf.length){
if(inLit){const n=Math.min(litRem,buf.length);litD+=buf.slice(0,n);buf=buf.slice(n);litRem-=n;
if(litRem===0){inLit=false;if(buf.startsWith('\r\n'))buf=buf.slice(2);responses.push('__LIT:'+litD);litD='';}else break;}
const i=buf.indexOf('\r\n');if(i===-1)break;
const l=buf.slice(0,i);buf=buf.slice(i+2);if(!l)continue;
const lm=l.match(/\{(\d+)\}$/);if(lm){inLit=true;litRem=parseInt(lm[1]);litD='';responses.push(l);continue;}
const tm=l.match(/^a(\d{3})\s+(OK|NO|BAD)\s+(.*)/);
if(tm&&pending['a'+tm[1]]){pending['a'+tm[1]]({l,status:tm[2],msg:tm[3],responses:[...responses]});responses=[];pending['a'+tm[1]]=null;}
else responses.push(l);}});
function send(t){return new Promise((res,rej)=>{tag++;const id='a'+String(tag).padStart(3,'0');pending[id]=res;sock.write(id+' '+t+'\r\n');setTimeout(()=>{if(pending[id]){delete pending[id];rej('TO');}},60000);});}
function decode(s){
  if(!s)return'';
  try{return s.replace(/=\?(UTF-8|utf-8)\?B\?([^?]+)\?=/g,(m,e,b)=>Buffer.from(b,'base64').toString('utf-8')).replace(/=\?(GB2312|gb2312|GBK|gbk)\?B\?([^?]+)\?=/g,(m,e,b)=>iconv.decode(Buffer.from(b,'base64'),'gbk'));}catch{return s;}
}

async function main(){
  await new Promise(r=>setTimeout(r,1500));
  await send(`LOGIN "${CFG.user}" "${CFG.pass}"`);

  for(const [id,enc] of EMAILS){
    await send(`SELECT "${enc}"`);
    const r=await send(`FETCH ${id} (BODY[])`);
    let raw=''; for(const resp of r.responses){if(resp.startsWith('__LIT:'))raw+=resp.slice(6);}
    if(!raw) continue;
    const parsed=await simpleParser(raw);
    const text=parsed.text||'';
    const from=parsed.from?.text||'';
    const subject=parsed.subject||'';
    const date=parsed.date||'';
    
    console.log(`\n${'='.repeat(60)}`);
    console.log(`📬 #${id} | ${subject}`);
    console.log(`   发件人: ${from} | ${date}`);
    console.log(`   正文:\n${text.slice(0,2000)}`);
  }
  
  await send('LOGOUT'); sock.end();
}

main().catch(e=>console.error(e));
