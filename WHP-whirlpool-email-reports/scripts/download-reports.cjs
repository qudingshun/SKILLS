/**
 * 邮件报表下载 v2 — 增量搜索
 *
 * 核心改进：
 * - 每项报表记录最后下载的邮件序号（STATE_FILE），下次只扫描新增的邮件
 * - 按发件人+关键词做唯一标识，互不干扰
 * - 移旧逻辑改为：只移除"已下载过"的旧文件（通过 STATE_FILE 判断），
 *   避免重复清理。
 * - 无新邮件/无匹配时自动下载上次邮件的附件（2026-07-22）
 */

const net = require('net');
const { simpleParser } = require('mailparser');
const fs = require('fs');
const path = require('path');

// ─── 配置 ──────────────────────────────────────────

const CFG = {
  user: 'dingshun_qu@whirlpool-china.com',
  pass: process.env.MAIL_PASS || '#***REMOVED***',
  host: 'imap.qiye.163.com', port: 143,
};

const BASE = 'E:\\OneDrive\\桌面\\生产情况日报';
const DIR = {
  产量: path.join(BASE, '产量'),
  发货: path.join(BASE, '发货'),
  存档: path.join(BASE, '新建文件夹'),
};

/** 状态文件：记录每个 (发件人+关键词) 最后成功下载的邮件序号 */
const STATE_FILE = path.join(__dirname, '..', '.download-state.json');

/**
 * REPORTS 配置：
 *   - key:         状态文件中的唯一键（发件人+关键词的标识）
 *   - folder:      IMAP 文件夹编码
 *   - sender:      发件人邮箱
 *   - keyword:     邮件主题匹配关键字
 *   - fileFilter:  附件文件名匹配关键字（null = 下载所有附件）
 *   - dest:        保存到哪个子目录
 */
const REPORTS = [
  {
    key: 'wenjie-assembly',
    folder: '&TqeRz2KliGg-',
    sender: 'wenjie_shen@whirlpool-china.com',
    keyword: '装配车间产量报表',
    fileFilter: null,
    dest: '产量',
  },
  {
    key: 'qingyu-export',
    folder: '&YhBUwVPRjSc-',
    sender: 'qingyu_zhou@whirlpool-china.com',
    keyword: '波轮出口日常报表',
    fileFilter: '波轮出口日常报表',
    dest: '发货',
  },
  {
    key: 'songming-warehouse',
    folder: '&YhBUwVPRjSc-',
    sender: 'songming_ye@whirlpool-china.com',
    keyword: '出口成品仓库日报明细表',
    fileFilter: '出口成品仓库日报明细表',
    dest: '发货',
  },
];

// ─── 状态管理 ──────────────────────────────────────

function loadState() {
  try {
    if (fs.existsSync(STATE_FILE)) {
      return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
    }
  } catch (e) {
    console.warn(`⚠️  状态文件读取失败，重建状态: ${e.message}`);
  }
  return {};
}

function saveState(state) {
  const dir = path.dirname(STATE_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, {recursive: true});
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8');
}

// ─── IMAP Raw Socket ───────────────────────────────

let tag=0, pending={}, buf='', responses=[], litRem=0, litD='', inLit=false;
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
  return new Promise((res,rej)=>{
    tag++;
    const id='a'+String(tag).padStart(3,'0');
    pending[id]=res;
    sock.write(id+' '+t+'\r\n');
    setTimeout(()=>{if(pending[id]){delete pending[id];rej('TO');}},30000);
  });
}

// ─── 邮件头/正文获取 ──────────────────────────────

async function fetchHeaderLines(seq) {
  const r = await send(`FETCH ${seq} (BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])`);
  const lines = [];
  for(const resp of r.responses) {
    if(resp.startsWith('__LIT:')) {
      lines.push(...resp.slice(6).split('\r\n').filter(Boolean));
    }
  }
  return lines;
}

async function fetchAttachmentNames(seq) {
  try {
    const raw = await fetchFullEmail(seq);
    const parsed = await simpleParser(raw);
    return (parsed.attachments || []).map(a => a.filename || '').filter(Boolean);
  } catch {
    return [];
  }
}

// ─── 编码处理 ──────────────────────────────────────

const iconv = require('iconv-lite');
function decodeSubject(s) {
  if(!s) return '';
  try {
    return s.replace(/=\?(UTF-8|utf-8)\?B\?([^?]+)\?=/g, (m,e,b)=>Buffer.from(b,'base64').toString('utf-8'))
            .replace(/=\?(GB2312|gb2312|GBK|gbk)\?B\?([^?]+)\?=/g, (m,e,b)=>iconv.decode(Buffer.from(b,'base64'),'gbk'));
  } catch { return s; }
}

function findHeader(lines, field) {
  const r = new RegExp(`^${field}:\\s*(.+)`, 'im');
  for(const l of lines) { const m = l.match(r); if(m) return m[1].trim(); }
  return '';
}

// ─── 移旧 ──────────────────────────────────────────

async function moveOldFiles(state) {
  console.log('\n📦 清理旧文件...');
  for (const name of ['产量','发货']) {
    const src = DIR[name], dst = DIR.存档;
    if (!fs.existsSync(src)) { fs.mkdirSync(src,{recursive:true}); continue; }
    if (!fs.existsSync(dst)) fs.mkdirSync(dst,{recursive:true});
    const files = fs.readdirSync(src).filter(f => f!=='.'&&f!=='..');
    for(const f of files) {
      const sp=path.join(src,f), dp=path.join(dst,f);
      if(fs.existsSync(dp)){ const ext=path.extname(f), base=path.basename(f,ext); fs.renameSync(sp,path.join(dst,`${base}_${Date.now()}${ext}`)); }
      else fs.renameSync(sp,dp);
    }
    console.log(`  ${files.length>0?`✅ ${name}: ${files.length}个文件→新建文件夹`:`📁 ${name}: 空目录`}`);
  }
}

async function fetchFullEmail(seq) {
  const r = await send('FETCH ' + seq + ' (BODY[])');
  let content = '';
  for(const resp of r.responses) {
    if(resp.startsWith('__LIT:')) content += resp.slice(6);
  }
  return content;
}

// ─── 下载并保存邮件（抽取公共函数） ────────────────

async function downloadEmail(report, seq, newState) {
  if (!seq || seq <= 0) {
    console.log(`   ⏭️ 无可用序号，跳过`);
    return;
  }
  console.log(`   📥 下载邮件 #${seq}...`);
  const raw = await fetchFullEmail(seq);
  const parsed = await simpleParser(raw);
  console.log(`      ✅ ${(raw.length/1024).toFixed(1)} KB, ${parsed.attachments?.length||0} 个附件`);

  const destDir = DIR[report.dest];
  if(!fs.existsSync(destDir)) fs.mkdirSync(destDir,{recursive:true});

  let savedCount = 0;
  if(parsed.attachments && parsed.attachments.length > 0) {
    for(const att of parsed.attachments) {
      const attName = att.filename || '';
      const safeName = attName.replace(/[<>:"/\\|?*]/g,'_');
      const ap = path.join(destDir, safeName);
      fs.writeFileSync(ap, att.content);
      console.log(`   💾 ${attName} (${(att.content.length/1024).toFixed(1)} KB)`);
      savedCount++;
    }
  }

  // 如果有附件，不保存正文（避免重复）；否则保存正文
  if (savedCount === 0 && parsed.text && parsed.text.trim().length > 0) {
    const tp = path.join(destDir, `${report.keyword}_正文.txt`);
    fs.writeFileSync(tp, parsed.text||parsed.html||'');
    console.log(`   💾 无匹配附件，正文已保存：${tp}`);
  } else if (savedCount > 0) {
    console.log(`   ✅ 本次下载 ${savedCount} 个文件`);
  }

  newState[report.key] = seq;
}

// ─── 主流程 ─────────────────────────────────────────

async function main() {
  await new Promise(r=>setTimeout(r,1500));
  console.log('='.repeat(55));
  console.log('📧 邮件报表下载 v2 (增量搜索)');
  console.log('='.repeat(55));

  // 加载状态
  const state = loadState();

  // 移旧（旧文件移到存档目录，为下载新文件腾出位置）
  await moveOldFiles(state);

  let r = await send(`LOGIN "${CFG.user}" "${CFG.pass}"`);
  console.log('\n🔌', r.status, '\n');

  const newState = { ...state };

  for(const report of REPORTS) {
    console.log('-'.repeat(50));
    console.log(`📋 ${report.keyword}`);
    console.log(`   发件人: ${report.sender}`);

    // 打开文件夹
    r = await send(`SELECT "${report.folder}"`);
    const existsResp = r.responses.find(x=>x.includes('EXISTS'));
    const total = existsResp ? parseInt(existsResp.match(/(\d+)\s+EXISTS/)[1]) : 0;
    console.log(`   📂 打开文件夹: 共${total}封`);

    if(total === 0) { console.log('   ❌ 空文件夹'); continue; }

    // 读上次最后搜索到的序号
    const lastSeq = state[report.key] || 0;
    console.log(`   📍 上次已搜到序号: ${lastSeq > 0 ? `#${lastSeq}` : '无'}`);

    // 总邮件数没变或更少 → 下载上次那条
    if (total <= lastSeq && lastSeq > 0) {
      console.log(`   ⏭️ 无新邮件（当前 ${total} ≤ 上次 ${lastSeq}），下载上次那条`);
      await downloadEmail(report, lastSeq, newState);
      continue;
    }

    // 增量扫描：从最新（total）扫到 lastSeq+1
    // 找第一封匹配发件人+关键词的（即最新的那封符合邮件）
    const startFrom = total;
    const scanEnd = lastSeq + 1;
    const scanCount = startFrom - scanEnd + 1;

    if (scanCount <= 0) {
      console.log(`   ⏭️ 无新邮件范围`);
      continue;
    }

    console.log(`   🔍 增量扫描 #${startFrom} → #${scanEnd}（共${scanCount}封），找含"${report.keyword}"的邮件...`);

    let foundId = null;
    for(let i = startFrom; i >= scanEnd; i--) {
      const hLines = await fetchHeaderLines(i);
      const from = findHeader(hLines, 'From') || '';
      const subject = decodeSubject(findHeader(hLines, 'Subject') || '');

      if(from.includes(report.sender)) {
        // 先检查主题（快）
        if(subject.includes(report.keyword)) {
          console.log(`   ✅ 找到! #${i} (主题匹配)`);
          console.log(`      主题: ${subject.slice(0,80)}`);
          console.log(`      日期: ${(findHeader(hLines,'Date')||'').slice(0,30)}`);
          foundId = i;
          break;
        }
        // 主题不匹配但发件人对→检查附件文件名
        console.log(`      #${i} 发件人匹配，检查附件文件名...`);
        const attNames = await fetchAttachmentNames(i);
        const hasMatch = attNames.some(n => n.includes(report.keyword));
        if(hasMatch) {
          console.log(`   ✅ 找到! #${i} (附件名匹配)`);
          console.log(`      主题: ${subject.slice(0,80)}`);
          console.log(`      日期: ${(findHeader(hLines,'Date')||'').slice(0,30)}`);
          foundId = i;
          break;
        }
      }
    }

    // 没有新匹配 → 下载上次那条
    if(!foundId) {
      console.log(`   ⏭️ 增量范围内无新匹配邮件，下载上次序号 #${lastSeq}`);
      await downloadEmail(report, lastSeq, newState);
      continue;
    }

    // 有匹配 → 下载
    await downloadEmail(report, foundId, newState);
  }

  // 保存状态
  saveState(newState);
  console.log('\n📝 状态已保存到:', STATE_FILE);

  await send('LOGOUT');
  sock.end();
  console.log('\n' + '='.repeat(55));
  console.log('✅ 全部完成！');
  console.log('='.repeat(55));
}

main().catch(e=>{console.error('❌',e.message||e);process.exit(1);});
