/**
 * 邮件下载 - 手动遍历最近邮件，本地筛选
 * 绕过 qiye.163.com IMAP SEARCH 不支持 FROM/SUBJECT 中文搜索的缺陷
 */
const net = require('net');
const { simpleParser } = require('mailparser');
const fs = require('fs');
const path = require('path');

const CFG = {
  user: 'dingshun_qu@whirlpool-china.com',
  pass: process.env.MAIL_PASS || '',
  host: 'imap.qiye.163.com', port: 143,
};

const BASE = 'E:/OneDrive/桌面/生产情况日报';
const DIR = {
  产量: path.join(BASE, '产量'),
  发货: path.join(BASE, '发货'),
  存档: path.join(BASE, '新建文件夹'),
};

const REPORTS = [
  {
    folder: '&TqeRz2KliGg-',
    sender: 'wenjie_shen@whirlpool-china.com',
    keyword: '装配车间产量报表',
    fileFilter: null,
    dest: '产量',
  },
  {
    folder: '&YhBUwVPRjSc-',
    sender: 'qingyu_zhou@whirlpool-china.com',
    keyword: '波轮出口日常报表',
    fileFilter: '波轮出口日常报表',
    attachmentOnly: true,   // 主题可能被改动 → 只按"附件名"命中，主题仅作展示
    dest: '发货',
  },
  {
    folder: '&YhBUwVPRjSc-',
    sender: 'songming_ye@whirlpool-china.com',
    keyword: '出口成品仓库日报明细表',
    fileFilter: '出口成品仓库日报明细表',
    dest: '发货',
  },
];

const iconv = require('iconv-lite');
function decodeSubject(s) {
  if(!s) return '';
  try {
    return s.replace(/=\?(UTF-8|utf-8)\?B\?([^?]+)\?=/g, (m,e,b)=>Buffer.from(b,'base64').toString('utf-8'))
            .replace(/=\?(GB2312|gb2312|GBK|gbk)\?B\?([^?]+)\?=/g, (m,e,b)=>iconv.decode(Buffer.from(b,'base64'),'gbk'));
  } catch { return s; }
}

function findHeader(lines, field) {
  const r = new RegExp('^'+field+':\s*(.+)', 'im');
  for(const l of lines) { const m = l.match(r); if(m) return m[1].trim(); }
  return '';
}

let tag=0,pending={},buf='',responses=[],litRem=0,litD='',inLit=false;
const sock = net.connect(CFG.port, CFG.host);
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

function send(t){
  return new Promise((res,rej)=>{tag++;const id='a'+String(tag).padStart(3,'0');pending[id]=res;sock.write(id+' '+t+'\r\n');setTimeout(()=>{if(pending[id]){delete pending[id];rej('TO');}},30000);});
}

async function fetchHeaderLines(seq) {
  const r = await send('FETCH '+seq+' (BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])');
  const lines = [];
  for(const resp of r.responses) {
    if(resp.startsWith('__LIT:')) {
      const content = resp.slice(6);
      lines.push(...content.split('\r\n').filter(Boolean));
    }
  }
  return lines;
}

async function fetchFullEmail(seq) {
  const r = await send('FETCH ' + seq + ' (BODY[])');
  let content = '';
  for(const resp of r.responses) {
    if(resp.startsWith('__LIT:')) content += resp.slice(6);
  }
  return content;
}

async function moveOldFiles() {
  console.log('\n📦 清理旧文件...');
  for (const name of ['产量','发货']) {
    const src = DIR[name], dst = DIR.存档;
    if (!fs.existsSync(src)) { fs.mkdirSync(src,{recursive:true}); continue; }
    if (!fs.existsSync(dst)) fs.mkdirSync(dst,{recursive:true});
    const files = fs.readdirSync(src).filter(f => f!== '.' && f!== '..');
    for(const f of files) {
      const sp=path.join(src,f), dp=path.join(dst,f);
      if(fs.existsSync(dp)){ const ext=path.extname(f), base=path.basename(f,ext); fs.renameSync(sp,path.join(dst,base+'_'+Date.now()+ext)); }
      else fs.renameSync(sp,dp);
    }
    console.log('  '+ (files.length>0? '✅ '+name+': '+files.length+'个文件→新建文件夹': '📁 '+name+': 空目录'));
  }
}

async function main() {
  await new Promise(r=>setTimeout(r,1500));
  console.log('='.repeat(55));
  console.log('📧 邮件报表下载');
  console.log('='.repeat(55));

  await moveOldFiles();

  let r = await send('LOGIN "'+CFG.user+'" "'+CFG.pass+'"');
  console.log('\n🔌', r.status, '\n');

  for(const report of REPORTS) {
    console.log('-'.repeat(50));
    console.log('📋 '+report.keyword);
    console.log('   发件人: '+report.sender);

    r = await send('SELECT "'+report.folder+'"');
    const exists = r.responses.find(x=>x.includes('EXISTS'));
    const total = exists ? parseInt(exists.match(/(\d+)\s+EXISTS/)[1]) : 0;
    console.log('   📂 打开文件夹: 共'+total+'封');

    if(total === 0) { console.log('   ❌ 空文件夹'); continue; }

    const scanCount = Math.min(500, total);
    // attachmentOnly 模式：发件人命中后拉全文看附件名，未命中则继续往前找（最多试 MAX_FULL_FETCH 封）
    const byAtt = !!report.attachmentOnly;
    const MAX_FULL_FETCH = 30;
    const rule = byAtt
      ? '发件人含 "'+report.sender+'" 且附件名含"'+report.fileFilter+'"（不卡主题）'
      : '发件人含 "'+report.sender+'" 且主题含"'+report.keyword+'"';
    console.log('   🔍 从最新开始扫描'+scanCount+'封，匹配: '+rule);

    let found = null;   // { id, raw, parsed, subject, date }
    let tried = 0;
    for(let i = total; i > total - scanCount; i--) {
      const hLines = await fetchHeaderLines(i);
      const from = findHeader(hLines, 'From') || '';
      const subject = decodeSubject(findHeader(hLines, 'Subject') || '');

      if(!from.includes(report.sender)) continue;
      if(!byAtt && !subject.includes(report.keyword)) continue;

      tried++;
      if(byAtt && tried > MAX_FULL_FETCH) { console.log('   ⚠️ 已检查'+MAX_FULL_FETCH+'封候选邮件仍无匹配附件，停止往前扫'); break; }

      const raw = await fetchFullEmail(i);
      const parsed = await simpleParser(raw);
      if(byAtt && !(parsed.attachments||[]).some(a => (a.filename||'').includes(report.fileFilter))) {
        console.log('   ⏭️ #'+i+' 主题「'+subject.slice(0,40)+'」无匹配附件，继续往前找');
        continue;
      }

      console.log('   ✅ 找到! #'+i);
      console.log('      主题: '+subject.slice(0,80));
      console.log('      日期: '+(findHeader(hLines,'Date')||'').slice(0,30));
      found = { id:i, raw, parsed, subject };
      break;
    }

    if(!found) {
      console.log('   ❌ 未在最近'+scanCount+'封中找到匹配邮件');
      continue;
    }

    console.log('   📥 下载邮件 #'+found.id+'...');
    const parsed = found.parsed;
    console.log('      ✅ '+(found.raw.length/1024).toFixed(1)+' KB, '+ (parsed.attachments?.length||0)+' 个附件');

    const destDir = DIR[report.dest];
    if(!fs.existsSync(destDir)) fs.mkdirSync(destDir,{recursive:true});

    let savedCount = 0;
    if(parsed.attachments && parsed.attachments.length > 0) {
      for(const att of parsed.attachments) {
        const attName = att.filename || '';
        if (report.fileFilter && !attName.includes(report.fileFilter)) {
          console.log('   ⏭️ 跳过: '+attName+'（不含"'+report.fileFilter+'"）');
          continue;
        }
        const safeName = attName.replace(/[<>:"/\\|?*]/g,'_');
        const ap = path.join(destDir, safeName);
        fs.writeFileSync(ap, att.content);
        console.log('   💾 '+attName+' ('+(att.content.length/1024).toFixed(1)+' KB)');
        savedCount++;
      }
    }

    if (savedCount === 0) {
      const tp = path.join(destDir, report.keyword+'_正文.txt');
      fs.writeFileSync(tp, parsed.text||parsed.html||'');
      console.log('   💾 无匹配附件，正文已保存: '+tp);
    } else {
      console.log('   ✅ 本次下载 '+savedCount+' 个文件');
    }
  }

  await send('LOGOUT');
  sock.end();
  console.log('\n' + '='.repeat(55));
  console.log('✅ 全部完成！');
  console.log('='.repeat(55));
}

main().catch(e=>{console.error('❌',e.message||e);process.exit(1);});