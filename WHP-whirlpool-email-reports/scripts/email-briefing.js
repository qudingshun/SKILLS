/**
 * 邮件简报 v2 - 快速扫描昨天今天新邮件
 */
const net = require('net');
const iconv = require('iconv-lite');

const CFG = {
  user: 'dingshun_qu@whirlpool-china.com',
  pass: '#***REMOVED***',
  host: 'imap.qiye.163.com', port: 143,
};

const FOLDERS = [
  ['INBOX','收件箱'],['&TqeRz2KliGg-','产量报表'],['&YhBUwVPRjSc-','成品发货'],
  ['&dR9Op4uhUhI-','生产计划'],['&WRaNOFbilh8-','外贸团队'],['&TrpUWJcAbEI-','人员需求'],
  ['&UXZO1mXlZwhipYho-','其他日月报表'],['&UXZO1pCuTvY-','其他邮件'],
  ['&UXNTVX7fi6E-','关单统计'],['&g0l6P3ux-','草稿箱'],['&XfJT0ZAB-','已发送'],
  ['&XfJSIJZk-','已删除'],['&V4NXPpCuTvY-','垃圾邮件'],['&dcVr0pCuTvY-','病毒邮件'],
  ['&Xn9USpCuTvY-','广告邮件'],['&g0l6Pw-','草稿'],
];

const KEYWORDS = {
  '配件':'🔧','订单':'📋','PO':'📋','物料':'📦','交货':'🚚',
  '库存':'📊','编码':'🏷️','价格':'💰','合同':'📄',
};

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
function send(t){return new Promise((res,rej)=>{tag++;const id='a'+String(tag).padStart(3,'0');pending[id]=res;sock.write(id+' '+t+'\r\n');setTimeout(()=>{if(pending[id]){delete pending[id];rej('TO');}},30000);});}

function decode(s){if(!s)return'';try{return s.replace(/=\?(UTF-8|utf-8)\?B\?([^?]+)\?=/g,(m,e,b)=>Buffer.from(b,'base64').toString('utf-8')).replace(/=\?(GB2312|gb2312|GBK|gbk)\?B\?([^?]+)\?=/g,(m,e,b)=>iconv.decode(Buffer.from(b,'base64'),'gbk'));}catch{return s;}}

function now(){const d=new Date();return `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日`;}
function imapDate(d){const m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];return `${d.getDate()}-${m[d.getMonth()]}-${d.getFullYear()}`;}

function getKeywords(s){
  const found=[];
  for(const[kw,tag] of Object.entries(KEYWORDS)){
    if(s.includes(kw)) found.push(tag);
  }
  return found.length>0 ? found.join('') : null;
}

async function main() {
  await new Promise(r=>setTimeout(r,1500));
  await send(`LOGIN "${CFG.user}" "${CFG.pass}"`);

  const today=new Date(), yesterday=new Date(today);
  yesterday.setDate(yesterday.getDate()-1);
  const since=imapDate(yesterday);
  const ymdY=`${yesterday.getFullYear()}-${String(yesterday.getMonth()+1).padStart(2,'0')}-${String(yesterday.getDate()).padStart(2,'0')}`;
  const ymdT=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

  console.log(`📧 邮件简报 — ${now()}`);
  console.log(`   扫描范围: ${ymdY} ~ ${ymdT}`);
  console.log('='.repeat(55));

  let allEmails=[], importantEmails=[];
  let totalFound=0;

  for(const [enc,dec] of FOLDERS){
    await send(`SELECT "${enc}"`);
    const r=await send(`SEARCH SINCE ${since}`);
    const sList=r.responses.find(x=>x.startsWith('* SEARCH'));
    const ids=sList?sList.replace('* SEARCH','').trim().split(/\s+/).filter(Boolean).map(Number):[];
    if(ids.length===0) continue;
    totalFound+=ids.length;

    console.log(`\n📁 ${dec} (${ids.length})`);

    // Show all in this folder (up to 8)
    const showIds=ids.slice(-8);
    for(const id of showIds){
      const hr=await send(`FETCH ${id} (BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])`);
      const lit=hr.responses.find(x=>x.startsWith('__LIT:'));
      if(!lit) continue;
      const lines=lit.slice(6).split('\r\n');
      let from='',subject='',date='';
      for(const l of lines){
        const f=l.match(/^From:\s*(.+)/im); if(f) from=f[1].trim();
        const s=l.match(/^Subject:\s*(.+)/im); if(s) subject=decode(s[1]);
        const d=l.match(/^Date:\s*(.+)/im); if(d) date=d[1].trim();
      }

      const tags=getKeywords(subject);
      const prefix=tags?tags+' ':'  ';
      console.log(`  ${prefix}#${id} | ${subject.slice(0,60)}`);

      if(tags){
        importantEmails.push({id,folder:dec,from:from.slice(0,50),subject:subject.slice(0,80),date:date.slice(0,25),tags});
      }
    }
    if(ids.length>8) console.log(`  ... 还有 ${ids.length-8} 封`);
  }

  // Summary
  console.log('\n'+'='.repeat(55));
  console.log(`📊 共扫描 ${FOLDERS.length} 个文件夹，${totalFound} 封新邮件`);
  if(importantEmails.length===0){
    console.log('⭐ 无特别标注的重点邮件');
  }else{
    console.log(`⭐ ${importantEmails.length} 封重点邮件:\n`);
    for(const e of importantEmails){
      console.log(`${e.tags} [${e.folder}] #${e.id}`);
      console.log(`   主题: ${e.subject}`);
      console.log(`   发件人: ${e.from}`);
      console.log(`   日期: ${e.date}\n`);
    }
  }

  await send('LOGOUT'); sock.end();
}

main().catch(e=>{console.error('❌',e.message||e);process.exit(1);});
