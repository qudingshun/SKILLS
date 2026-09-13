/**
 * 邮件简报 → Excel v3
 * 优化: 减少 IMAP 往返, 只取正文文本部分, 排除邮箱地址误匹配
 */
const net = require('net');
const { simpleParser } = require('mailparser');
const iconv = require('iconv-lite');
const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');

const CFG = {user:'dingshun_qu@whirlpool-china.com',pass:'#***REMOVED***',host:'imap.qiye.163.com',port:143};
const FOLDERS = [
  ['INBOX','收件箱'],['&TqeRz2KliGg-','产量报表'],['&YhBUwVPRjSc-','成品发货'],
  ['&dR9Op4uhUhI-','生产计划'],['&WRaNOFbilh8-','外贸团队'],['&TrpUWJcAbEI-','人员需求'],
  ['&UXZO1mXlZwhipYho-','其他日月报表'],['&UXZO1pCuTvY-','其他邮件'],['&UXNTVX7fi6E-','关单统计'],
  ['&g0l6P3ux-','草稿箱'],['&XfJT0ZAB-','已发送'],['&XfJSIJZk-','已删除'],
  ['&V4NXPpCuTvY-','垃圾邮件'],['&dcVr0pCuTvY-','病毒邮件'],['&Xn9USpCuTvY-','广告邮件'],['&g0l6Pw-','草稿'],
];
const KEYWORDS = {'配件':'🔧','订单':'📋','PO':'📋','物料':'📦','交货':'🚚','库存':'📊','编码':'🏷️','价格':'💰','合同':'📄'};

// ===== IMAP Client =====
let tag=0,pending={},buf='',responses=[],litRem=0,litD='',inLit=false,currentFolder='';
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
async function selectFolder(enc){
  if(enc===currentFolder) return;
  await send(`SELECT "${enc}"`);
  currentFolder=enc;
}

function decode(s){
  if(!s)return'';
  try{return s.replace(/=\?(UTF-8|utf-8)\?B\?([^?]+)\?=/g,(m,e,b)=>Buffer.from(b,'base64').toString('utf-8')).replace(/=\?(GB2312|gb2312|GBK|gbk)\?B\?([^?]+)\?=/g,(m,e,b)=>iconv.decode(Buffer.from(b,'base64'),'gbk'));}catch{return s;}
}
function imapDate(d){const m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];return `${d.getDate()}-${m[d.getMonth()]}-${d.getFullYear()}`;}
function getKeywords(s){const f=[];for(const[k,t]of Object.entries(KEYWORDS)){if(s.includes(k))f.push(t);}return f.length>0?[...new Set(f)].join(' '):'';}

function extractFromBody(text){
  if(!text)return[];
  const items=[];
  // 表格: 编码+型号+数量
  let m;const t1=/([A-Z0-9]{5,})\s+([A-Z0-9\*\-]{4,})\s+(\d{2,})/g;while((m=t1.exec(text))!==null)items.push(`编码:${m[1]} 型号:${m[2]} 数量:${m[3]}`);
  // 表格: 编码+中文名+数量
  const t2=/([A-Z0-9]{5,})\s+([\u4e00-\u9fff]+)\s+(\d+)/g;while((m=t2.exec(text))!==null)items.push(`编码:${m[1]} 名称:${m[2]} 数量:${m[3]}`);
  // 订单号 (排除邮箱)
  const t3=/(?:订单号|PO|SO)[：:\s]*([A-Za-z0-9\-_]{5,})/g;while((m=t3.exec(text))!==null){const v=m[1];if(!v.includes('@')&&!v.includes('.com')&&!/^[a-z]{2,}$/i.test(v))items.push(`订单号:${v}`);}
  // 编码标签
  const t4=/(?:编码|料号|工厂编码|物料编码|零件号)[：:\s]*([A-Za-z0-9\-_\/]{5,})/gi;while((m=t4.exec(text))!==null)items.push(`编码:${m[1]}`);
  // 型号
  const t5=/(?:型号|产品型号|整机型号)[：:\s]*([\*A-Za-z0-9\-_\/\(\)]{4,})/gi;while((m=t5.exec(text))!==null)items.push(`型号:${m[1]}`);
  // 数量
  const t6=/(?:数量|订单数|Q'ty|Qty|订单数量)[：:\s]*(\d+)/gi;while((m=t6.exec(text))!==null)items.push(`数量:${m[1]}`);
  // 物料名称
  const t7=/(?:物料名称)[：:\s]*([\u4e00-\u9fff\w]+)/gi;while((m=t7.exec(text))!==null)items.push(`物料:${m[1]}`);
  return [...new Set(items)].slice(0,30);
}

async function main(){
  await new Promise(r=>setTimeout(r,1500));
  await send(`LOGIN "${CFG.user}" "${CFG.pass}"`);

  const today=new Date(),yesterday=new Date(today);yesterday.setDate(yesterday.getDate()-1);
  const since=imapDate(yesterday);
  const now=new Date();
  const dateStr=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  const hourStr=String(now.getHours()).padStart(2,'0');
  const outFile=path.join('E:\\OneDrive\\桌面',`${dateStr}_${hourStr}时邮件简报.xlsx`);

  const allRows=[]; const importantRows=[];
  let totalFound=0;

  for(const [enc,dec] of FOLDERS){
    await selectFolder(enc);
    const r=await send(`SEARCH SINCE ${since}`);
    const sList=r.responses.find(x=>x.startsWith('* SEARCH'));
    const ids=sList?sList.replace('* SEARCH','').trim().split(/\s+/).filter(Boolean).map(Number):[];
    if(ids.length===0) continue;
    totalFound+=ids.length;

    for(const id of ids){
      const hr=await send(`FETCH ${id} (BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])`);
      const lit=hr.responses.find(x=>x.startsWith('__LIT:'));
      if(!lit) continue;
      const lines=lit.slice(6).split('\r\n');
      let from='',subject='',date='';
      for(const l of lines){
        const f=l.match(/^From:\s*(.+)/im);if(f)from=decode(f[1]).trim();
        const s=l.match(/^Subject:\s*(.+)/im);if(s)subject=decode(s[1]);
        const d=l.match(/^Date:\s*(.+)/im);if(d)date=d[1].trim();
      }
      const tags=getKeywords(subject);
      allRows.push({folder:dec,id,from:from.slice(0,60),subject:subject.slice(0,100),date:date.slice(0,30),tags});
      if(tags) importantRows.push({id,enc,dec,subject,from,date,tags});
    }
  }

  // 展开重点邮件 - 批量按文件夹处理
  console.log(`\n📥 展开 ${importantRows.length} 封重点邮件...`);
  
  // 按文件夹分组
  const byFolder={};
  for(const e of importantRows){
    if(!byFolder[e.enc]) byFolder[e.enc]={dec:e.dec,ids:[]};
    byFolder[e.enc].ids.push(e.id);
  }

  for(const [enc,info] of Object.entries(byFolder)){
    await selectFolder(enc);
    for(const id of info.ids){
      process.stdout.write(`  [${info.dec}] #${id}...`);
      try{
        // 先取一段正文 (BODY[1] = 第一个文本部分)
        // 用 BODY[TEXT] 获取完整的正文内容（不含附件）
        const r=await send(`FETCH ${id} (BODY.PEEK[TEXT])`);
        const lit=r.responses.find(x=>x.startsWith('__LIT:'));
        if(lit){
          const raw=lit.slice(6);
          // 直接用 simpleParser 解析完整邮件（TEXT = headers + body without attachments）
          try {
            // 对于纯 text/plain 或 text/html，直接作为文本处理
            const bodyClean=raw.replace(/^Content-(Type|Transfer-Encoding|Disposition):[^\n]*\n/igm,'').trim();
            const email=importantRows.find(e=>e.id===id);
            
            // 判断是不是结构化 MIME
            if(raw.includes('Content-Type: multipart') || raw.includes('Content-Type: text')){
              // 尝试解码 GB2312 + base64
              let body=''; let html='';
              const isGB2312B64=raw.match(/charset="?GB2312"?.*Content-Transfer-Encoding:\s*base64/);
              if(isGB2312B64){
                const b64=raw.split('\n').filter(l=>!/^(Content|-----)/.test(l)&&l.trim()).join('');
                try{
                  const dec=iconv.decode(Buffer.from(b64,'base64'),'gbk');
                  body=dec.replace(/\r\n/g,'\n');
                }catch(e){/*fallback*/}
              }
              if(!body){
                const parsed=await simpleParser(raw);
                body=(parsed.text||'').replace(/\r\n/g,'\n');
                html=(parsed.html||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
              }
              const allText=body||html;
              email.bodyPreview=body.replace(/\n/g,' ').slice(0,300);
              email.bodyFull=body;
              email.details=extractFromBody(allText).join('; ');
            } else {
              // 纯文本
              email.bodyPreview=bodyClean.replace(/\n/g,' ').slice(0,300);
              email.bodyFull=bodyClean;
              email.details=extractFromBody(bodyClean).join('; ');
            }
            console.log(` ${email.details||'✅'}`);
          } catch(e2){
            // 直接作为文本
            const email=importantRows.find(e=>e.id===id);
            email.bodyPreview=raw.replace(/\n/g,' ').slice(0,300);
            email.bodyFull=raw;
            email.details=extractFromBody(raw).join('; ');
            console.log(` ${email.details||'✅(raw)'}`);
          }
        } else {
          console.log(' ⚠️ 无正文');
        }
      } catch(e){
        console.log(` ⚠️ ${e.message.slice(0,40)}`);
      }
    }
  }

  await send('LOGOUT'); sock.end();

  // 更新汇总
  for(const row of allRows){
    const imp=importantRows.find(e=>e.id===row.id);
    if(imp){row.details=imp.details||'';row.bodyPreview=imp.bodyPreview||'';row.attachments=imp.attachments||'';}
  }

  // 生成 Excel
  const wb=XLSX.utils.book_new();
  
  const h1=['文件夹','序号','发件人','主题','日期','重要标记','提取信息'];
  const d1=allRows.map(r=>[r.folder,r.id,r.from||'',r.subject||'',r.date||'',r.tags||'',r.details||'']);
  const ws1=XLSX.utils.aoa_to_sheet([h1,...d1]);
  ws1['!cols']=[{wch:12},{wch:6},{wch:28},{wch:45},{wch:25},{wch:10},{wch:50}];
  XLSX.utils.book_append_sheet(wb,ws1,'邮件汇总');

  const h2=['文件夹','序号','发件人','主题','日期','标记','附件','正文摘要','提取信息'];
  const d2=importantRows.map(r=>[r.dec||r.folder,r.id,r.from||'',r.subject||'',r.date||'',r.tags||'',r.attachments||'',r.bodyPreview||'',r.details||'']);
  const ws2=XLSX.utils.aoa_to_sheet([h2,...d2]);
  ws2['!cols']=[{wch:12},{wch:6},{wch:28},{wch:45},{wch:25},{wch:10},{wch:30},{wch:55},{wch:55}];
  XLSX.utils.book_append_sheet(wb,ws2,'重点邮件详情');

  const fc={};for(const r of allRows){fc[r.folder]=(fc[r.folder]||0)+1;}
  const s1=[['📊 邮件简报统计'],[''],['生成时间',`${dateStr} ${hourStr}:00`],['扫描范围',`${yesterday.toLocaleDateString()}~${today.toLocaleDateString()}`],['总邮件数',allRows.length],['重点邮件数',importantRows.length],['',''],['---各文件夹---',''],...Object.entries(fc).sort((a,b)=>b[1]-a[1])];
  const ws3=XLSX.utils.aoa_to_sheet(s1);
  ws3['!cols']=[{wch:25},{wch:15}];
  XLSX.utils.book_append_sheet(wb,ws3,'统计汇总');

  // Sheet 4: 订单信息
  const orderData=buildOrderSheet(importantRows);
  if(orderData.length>1){
    const ws4=XLSX.utils.aoa_to_sheet(orderData);
    ws4['!cols']=[{wch:20},{wch:20},{wch:25},{wch:12},{wch:15},{wch:15},{wch:20}];
    XLSX.utils.book_append_sheet(wb,ws4,'订单信息');
  }

  XLSX.writeFile(wb,outFile);
  console.log(`\n✅ ${outFile}  (${allRows.length}封/${importantRows.length}重点/${(fs.statSync(outFile).size/1024).toFixed(1)}KB)`);
}

/**
 * 从重点邮件正文中提取结构化订单信息
 */
function buildOrderSheet(importantRows){
  const rows=[['来源','编码/订单号','型号/物料名称','数量','交期/备注','国家/市场','采购员']];
  
  for(const email of importantRows){
    const body=email.bodyFull||email.bodyPreview||'';
    const subj=email.subject||'';
    
    // 拉美订单 (#2452) - 国家+编码+型号+数量+交期
    if(subj.includes('拉美')||subj.includes('洗衣机')){
      const re=/([A-Z]{3,}(?:\s+[A-Z]{3,})?)\s+([A-Z0-9]{6,})\s+([A-Z0-9\*\-]{4,})\s+(\d{2,})\s+(\d+月)/g;
      let m;
      while((m=re.exec(body))!==null){
        const country=m[1].trim();
        if(country.length<25&&/[A-Z]/.test(country)&&!country.includes('编码')&&!country.includes('型号')){
          rows.push([`拉美订单`,m[2],m[3],parseInt(m[4]),m[5],country,'']);
        }
      }
    }
    
    // 澳洲 Kogan 订单 (#9821) - 编码+型号+数量台
    if(subj.includes('Kogan')||subj.includes('澳洲')){
      const re=/([A-Z0-9]{5,})\s+\*?([A-Z0-9\*\(\)\-\u4e00-\u9fff]+)\(?[A-Za-z\u4e00-\u9fff]*\)?\s+(\d+)台?/g;
      let m;
      while((m=re.exec(body))!==null){
        if(!m[1].includes('@')) rows.push([`澳洲Kogan`,m[1],m[2].replace(/[\(\)]/g,''),parseInt(m[3]),'6月','澳洲','']);
      }
    }
    
    // 大连万博配件 (#2453) - 订单号+编码+物料名称+数量
    if(subj.includes('配件')||subj.includes('大连')){
      // Try structured format: 编码+中文名+数量
      const re=/([A-Z0-9]{5,})\s+([\u4e00-\u9fff\w]+)\s+(\d+)\s+\*?([A-Z0-9\*\(\)\-\u4e00-\u9fff]+)/g;
      let m;
      while((m=re.exec(body))!==null){
        const exists=rows.some(r=>r[1]===m[1]&&r[0]==='配件P112832');
        if(!exists) rows.push([`配件P112832`,m[1],m[2],parseInt(m[3]),m[4],'','']);
      }
      // Fallback for items without model
      if(rows.filter(r=>r[0]==='配件P112832').length<3){
        const simple=/([A-Z0-9]{5,})\s+([\u4e00-\u9fff]+)\s+(\d+)/g;
        while((m=simple.exec(body))!==null){
          const exists=rows.some(r=>r[1]===m[1]);
          if(!exists) rows.push([`配件P112832`,m[1],m[2],parseInt(m[3]),'*CLATA12K(摩洛哥)','','']);
        }
      }
    }
    
    // 台湾订单 (#2450) - 从GB2312解码的正文中提取
    if(subj.includes('台湾')||subj.includes('8月新订单')){
      const re=/([A-Z0-9]{5,})\s+([A-Z0-9\*\-]+)\s+(\d+)/g;
      let m;
      while((m=re.exec(body))!==null){
        if(m[1].length>=7){ // 台湾编码至少7位
          const exists=rows.some(r=>r[1]===m[1]&&r[0]==='台湾订单');
          if(!exists) rows.push([`台湾订单`,m[1],m[2],parseInt(m[3]),'8月5日','台湾','']);
        }
      }
    }
  }
  
  // 去重并保持顺序
  const unique=[];const seen=new Set();
  for(const r of rows){
    const key=r[0]+'|'+r[1];
    if(!seen.has(key)){seen.add(key);unique.push(r);}
  }
  return unique;
}

main().catch(e=>{console.error('\n❌',e.message||e);process.exit(1);});
