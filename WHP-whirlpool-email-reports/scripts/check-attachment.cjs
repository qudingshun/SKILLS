const net = require('net');
const { simpleParser } = require('mailparser');

const CFG = {user:'dingshun_qu@whirlpool-china.com',pass:'#***REMOVED***',host:'imap.qiye.163.com',port:143};

let tag=0;
const sock = net.connect(CFG.port,CFG.host);
sock.on('data',(d)=>{
  let buf=d.toString();
  while(buf.length){
    if(buf.indexOf('\r\n')===-1)break;
    const l=buf.slice(0,buf.indexOf('\r\n'));
    buf=buf.slice(buf.indexOf('\r\n')+2);
    if(!l)continue;
    console.log(l.trim());
  }
});

function send(t){
  return new Promise((res,rej)=>{
    tag++;
    const id='a'+String(tag).padStart(3,'0');
    const pending={}[id]=res;
    sock.write(id+' '+t+'\r\n');
    setTimeout(()=>{if(pending[id]){delete pending[id];rej('TO');}},60000);
  });
}

async function fetchFullEmail(seq){
  const r = await send('FETCH ' + seq + ' (BODY[])');
  let content='';
  for(const resp of r.responses){
    if(resp.startsWith('__LIT:'))content+=resp.slice(6);
  }
  return content;
}

async function main(){
  console.log('\n'+'='.repeat(50));
  console.log('检查邮件 #11144 附件情况');
  console.log('='.repeat(50));
  
  await send(`LOGIN "${CFG.user}" "${CFG.pass}"`);
  console.log('\n🔌 OK\n');
  
  const raw = await fetchFullEmail(11144);
  console.log('邮件 #11144 大小:',raw.length,'bytes');
  
  const parsed=await simpleParser(raw);
  console.log('附件数量:',parsed.attachments?.length||0);
  
  if(parsed.attachments){
    console.log('\n📎 附件列表:');
    parsed.attachments.forEach((a,i)=>{
      console.log(`  ${i+1}. ${a.filename} - ${(a.content.length/1024).toFixed(1)} KB`);
    });
    
    if(parsed.text){
      console.log('\n📝 正文预览（前 500 字）:');
      const lines = parsed.text.split('\n').filter(l=>l.trim()).slice(0,30);
      for(const l of lines) console.log(`  ${l.trim().slice(0,120)}`);
    } else if(parsed.html){
      console.log('\n📝 HTML 正文预览（前 500 字）:');
      const html = parsed.html.replace(/<[^>]+>/g,'').substring(0,500);
      console.log(html);
    }
  } else {
    console.log('❌ 无附件');
  }
  
  await send('LOGOUT'); sock.end();
}

main().catch(e=>{console.error('❌',e.message||e);process.exit(1);});
