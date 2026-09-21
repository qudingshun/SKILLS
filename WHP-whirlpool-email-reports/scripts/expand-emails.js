const net = require('net');
const { simpleParser } = require('mailparser');
const iconv = require('iconv-lite');

const CFG = {user:'dingshun_qu@whirlpool-china.com',pass:process.env.MAIL_PASS||'',host:'imap.qiye.163.com',port:143};

const EMAILS = [
  [9817,'收件箱','INBOX'],
  [9821,'收件箱','INBOX'], // 澳洲Kogan新订单
  [2450,'外贸团队','&WRaNOFbilh8-'], // 台湾新订单
  [2452,'外贸团队','&WRaNOFbilh8-'], // 拉美订单
  [2453,'外贸团队','&WRaNOFbilh8-'], // 大连万博配件
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

async function main() {
  await new Promise(r=>setTimeout(r,1500));
  await send(`LOGIN "${CFG.user}" "${CFG.pass}"`);

  for(const [id,dec,enc] of EMAILS){
    console.log(`\n`+'='.repeat(50));
    console.log(`📬 [${dec}] #${id}`);
    
    await send(`SELECT "${enc}"`);
    
    // Fetch full email body
    const r = await send(`FETCH ${id} (BODY[])`);
    let raw = '';
    for(const resp of r.responses){
      if(resp.startsWith('__LIT:')) raw += resp.slice(6);
    }
    
    if(!raw){
      console.log('  无法获取邮件内容');
      continue;
    }
    
    const parsed = await simpleParser(raw);
    const subject = parsed.subject || '';
    const from = parsed.from?.text || '';
    const date = parsed.date || '';
    const text = parsed.text || '';
    const html = parsed.html || '';
    const attachments = parsed.attachments || [];
    
    console.log(`  主题: ${subject}`);
    console.log(`  发件人: ${from}`);
    console.log(`  日期: ${date}`);
    
    // Show body text preview
    const body = text || html?.replace(/<[^>]+>/g,'') || '';
    console.log(`\n  📝 正文内容:`);
    const lines = body.split('\n').filter(l=>l.trim()).slice(0,30);
    for(const l of lines) console.log(`    ${l.trim().slice(0,120)}`);
    if(lines.length<3 && attachments.length>0) console.log('    (内容在附件中)');
    
    // Extract codes/quantities
    console.log(`\n  📋 提取信息:`);
    const codes = body.match(/(?:编码|料号|型号|零件号)[：:]*\s*([A-Za-z0-9\-_\/]+)/gi);
    if(codes) for(const c of codes.slice(0,10)) console.log(`    🏷️ ${c}`);
    
    const qtys = body.match(/(?:数量|个数|件数)[：:]*\s*(\d+[\d,\.]*)/gi);
    if(qtys) for(const q of qtys.slice(0,10)) console.log(`    🔢 ${q}`);
    
    const pos = body.match(/(?:PO|订单号|SO)[：:]*\s*([A-Za-z0-9\-_\/]{5,})/gi);
    if(pos) for(const p of pos.slice(0,10)) console.log(`    📋 ${p}`);

    // Show attachment info
    if(attachments.length>0){
      console.log(`\n  📎 附件 (${attachments.length} 个):`);
      for(const att of attachments){
        console.log(`    ${att.filename||'(无文件名)'} (${(att.content.length/1024).toFixed(1)} KB)`);
      }
    }
  }
  
  await send('LOGOUT'); sock.end();
}

main().catch(e=>{console.error('❌',e.message||e);process.exit(1);});
