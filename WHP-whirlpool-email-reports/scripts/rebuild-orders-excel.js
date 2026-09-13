/**
 * Rebuild orders Excel - clean version
 */
const net = require('net');
const { simpleParser } = require('mailparser');
const iconv = require('iconv-lite');
const XLSX = require('xlsx');

const CFG = {user:'dingshun_qu@whirlpool-china.com',pass:'#***REMOVED***',host:'imap.qiye.163.com',port:143};

// IMAP helpers
let tag=0,pending={},buf='',responses=[],litRem=0,litD='',inLit=false;
const sock=net.connect(CFG.port,CFG.host);
sock.on('data',d=>{buf+=d.toString();
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
function decode(s){if(!s)return'';try{return s.replace(/=\?(UTF-8|utf-8)\?B\?([^?]+)\?=/g,(m,e,b)=>Buffer.from(b,'base64').toString('utf-8')).replace(/=\?(GB2312|gb2312|GBK|gbk)\?B\?([^?]+)\?=/g,(m,e,b)=>iconv.decode(Buffer.from(b,'base64'),'gbk'));}catch{return s;}}

async function fetchBody(id,enc){
  await send('SELECT "'+enc+'"');
  let hr=await send('FETCH '+id+' (BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])');
  let lit=hr.responses.find(x=>x.startsWith('__LIT:'));
  let from='',subject='',date='';
  if(lit){for(const l of lit.slice(6).split('\r\n')){
    const f=l.match(/^From:\s*(.+)/im);if(f)from=decode(f[1]).trim();
    const s=l.match(/^Subject:\s*(.+)/im);if(s)subject=decode(s[1]);
    const d=l.match(/^Date:\s*(.+)/im);if(d)date=d[1].trim();
  }}
  hr=await send('FETCH '+id+' (BODY[])');
  let raw='';for(const r of hr.responses){if(r.startsWith('__LIT:'))raw+=r.slice(6);}
  let text='';
  if(raw){
    try{
      if(/GB2312.*base64/i.test(raw)){
        const b64=raw.split('\n').filter(l=>!/^(Content|-----)/i.test(l)&&!/^\s*$/.test(l)).join('');
        try{text=iconv.decode(Buffer.from(b64,'base64'),'gbk');}catch{}
      }
      if(!text){const p=await simpleParser(raw);text=p.text||'';}
    }catch{}
  }
  return {from,subject,date,text};
}

async function main(){
  await new Promise(r=>setTimeout(r,1500));
  await send('LOGIN "'+CFG.user+'" "'+CFG.pass+'"');
  console.log('Fetching emails...');

  const b={};
  b[9821]=await fetchBody(9821,'INBOX'); console.log('  #9821 Kogan');
  b[2450]=await fetchBody(2450,'&WRaNOFbilh8-'); console.log('  #2450 Taiwan');
  b[2452]=await fetchBody(2452,'&WRaNOFbilh8-'); console.log('  #2452 LatinAm');
  b[2453]=await fetchBody(2453,'&WRaNOFbilh8-'); console.log('  #2453 Dalian');

  await send('LOGOUT'); sock.end();

  // ====== Build Excel ======
  const wb = XLSX.utils.book_new();

  // === Sheet 1: Australia Kogan ===
  const kd=[['订单号','型号','数量','交期','备注'],
    ['301B2254','KAWWASHT15B(澳洲)','154台','6月','不涉及能效升级，正常备料']];
  const ws1=XLSX.utils.aoa_to_sheet([['[澳洲] Kogan 新订单 (#9821)'],[''],
    ['发件人:',b[9821].from],['日期:',b[9821].date],[''],...kd]);
  ws1['!cols']=[{wch:12},{wch:25},{wch:10},{wch:8},{wch:35}];
  XLSX.utils.book_append_sheet(wb,ws1,'澳洲Kogan');

  // === Sheet 2: Taiwan ===
  const t2=b[2450].text;
  const tw=[];
  let m;
  const haRe=/台湾\s+HA\s+(\w+)\s+(\w+)\s+(\d+)/g;while((m=haRe.exec(t2))!==null)tw.push(['HA',m[1],m[2],+m[3]]);
  const vaRe=/台湾\s+VA\s+(\w+)\s+(\w+)\s+(\d+)/g;while((m=vaRe.exec(t2))!==null)tw.push(['VA',m[1],m[2],+m[3]]);
  let haT=0,vaT=0;for(const r of tw){if(r[0]=='HA')haT+=r[3];if(r[0]=='VA')vaT+=r[3];}
  const twd=[['[台湾] 8月新订单 (#2450)'],[''],['发件人:',b[2450].from],['日期:',b[2450].date],['交期:','2026年8月5日'],[''],
    ['【HA 洗衣机】'],['品类','编码','型号','数量']];
  for(const r of tw.filter(x=>x[0]=='HA'))twd.push(r);
  twd.push(['','小计','',haT],[''],['【VA 干衣机】'],['品类','编码','型号','数量']);
  for(const r of tw.filter(x=>x[0]=='VA'))twd.push(r);
  twd.push(['','小计','',vaT],['','','总计',haT+vaT]);
  const ws2=XLSX.utils.aoa_to_sheet(twd);
  ws2['!cols']=[{wch:8},{wch:12},{wch:20},{wch:8}];
  XLSX.utils.book_append_sheet(wb,ws2,'台湾订单');

  // === Sheet 3: Latin America ===
  const b3=b[2452].text;
  const la=[];
  // Only process the latest section (before ----)
  const s3=b3.split(/-{4,}\s*\u56de\u590d\u7684\u539f\u90ae\u4ef6\s*-{4,}/);
  const s3latest=s3[0]||'';
  const laRe=/([A-Z\s]{4,25}?)\s+([A-Z0-9]{6,})\s+([A-Z0-9\*\-]{4,})\s+(\d{2,})\s+(\d+月)/g;
  while((m=laRe.exec(s3latest))!==null){const c=m[1].trim();
    if(c.length<25&&/[A-Z]/.test(c)&&!/编码|型号|工厂|产品|国家/.test(c)){
      la.push([c,m[2],m[3],+m[4],m[5],'\u672c\u8f6e(5/13)']);
    }
  }
  let j6=0,j7=0;for(const r of la){if(r[4].includes('6\u6708'))j6+=r[3];if(r[4].includes('7\u6708'))j7+=r[3];}
  const lad=[['[拉美] 洗衣机 26年6-7月订单 (#2452)'],[''],['发件人:',b[2452].from],['日期:',b[2452].date],[''],
    ['国家','编码','型号','数量','交期','批次']];
  for(const r of la)lad.push(r);
  lad.push(['','','6\u6708\u5408\u8ba1',j6,'',''],['','','7\u6708\u5408\u8ba1',j7,'',''],['','','\u603b\u8ba1',j6+j7,'','']);
  const ws3=XLSX.utils.aoa_to_sheet(lad);
  ws3['!cols']=[{wch:15},{wch:12},{wch:20},{wch:8},{wch:8},{wch:12}];
  XLSX.utils.book_append_sheet(wb,ws3,'拉美订单');

  // === Sheet 4: Dalian Parts ===
  const b4=b[2453].text;
  const pr=[['订单号','编码','物料名称','数量']];
  const prRe=/([A-Z0-9]{5,})\s+([\u4e00-\u9fff\w]+)\s+(\d+)/g;
  while((m=prRe.exec(b4))!==null){
    if(!pr.some(r=>r[1]===m[1]))pr.push(['P112832',m[1],m[2],+m[3]]);
  }
  const pd=[['[大连万博] 配件 P112832 (#2453)'],[''],['发件人:',b[2453].from],['日期:',b[2453].date],
    ['状态:','物料未领到，需加急，预计22号随大货发出'],[''],...pr];
  const ws4=XLSX.utils.aoa_to_sheet(pd);
  ws4['!cols']=[{wch:12},{wch:22},{wch:22},{wch:8}];
  XLSX.utils.book_append_sheet(wb,ws4,'大连万博配件');

  // === Sheet 5: Summary ===
  const sum=[['订单'],['澳洲 Kogan',kd[1][2],kd[1][3],'\ud83d\udfe1','#9821'],
    ['台湾 8月\u8ba2\u5355',haT+vaT+'台','8\u67085\u65e5','\ud83d\udfe2','#2450'],
    ['\u62c9\u7f8e 6-7\u6708',j6+j7+'台','6-7\u6708','\ud83d\udfe1','#2452'],
    ['\u5927\u8fde\u4e07\u535a\u914d\u4ef6',pr.length-1+'\u9879','\u672c\u670822\u65e5','\ud83d\udd34','#2453']];
  const ws5=XLSX.utils.aoa_to_sheet([['\ud83d\udcca \u8ba2\u5355\u4fe1\u606f\u6c47\u603b'],[''],
    ['\u8ba2\u5355','\u603b\u6570\u91cf','\u4ea4\u671f','\u7d27\u6025\u5ea6','\u6765\u6e90\u90ae\u4ef6'],...sum]);
  ws5['!cols']=[{wch:20},{wch:12},{wch:8},{wch:8},{wch:18}];
  XLSX.utils.book_append_sheet(wb,ws5,'\u6c47\u603b');

  const h=String(new Date().getHours()).padStart(2,'0');
  const f='E:\\OneDrive\\桌面\\2026-05-14_'+h+'\u65f6\u8ba2\u5355\u4fe1\u606f.xlsx';
  XLSX.writeFile(wb,f);
  console.log('\nDone: '+f);
  console.log('Sheets: '+wb.SheetNames.join(', '));
}

main().catch(e=>{console.error('ERR:',e.message||e);process.exit(1);});
