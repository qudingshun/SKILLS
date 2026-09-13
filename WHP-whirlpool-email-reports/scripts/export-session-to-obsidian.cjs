/**
 * export-session-to-obsidian.cjs
 *
 * v2.0 — 导出对话 + 知识点提取
 *
 * 输出:
 *   D:\Raw\openclaw-sessions\{date}\{title}.md              — 对话记录（含关联知识点链接）
 *   D:\Raw\openclaw-sessions\_knowledge\{keyword}.md         — 独立知识点卡片
 *   D:\Raw\openclaw-sessions\_knowledge\_index.md            — 知识索引
 *
 * 用法:
 *   node scripts/export-session-to-obsidian.cjs           # 当前会话增量导出
 *   node scripts/export-session-to-obsidian.cjs --all     # 所有活跃会话
 */
const fs = require('fs');
const path = require('path');

const SESSIONS_DIR = 'C:\\Users\\qudin\\.openclaw\\agents\\main\\sessions';
const OBSIDIAN_VAULT = 'D:\\Raw\\openclaw-sessions';
const KNOWLEDGE_DIR = path.join(OBSIDIAN_VAULT, '_knowledge');
const STATE_FILE = path.join(__dirname, '..', '.export-state.json');

// ======== 工具函数 ========

function pad(n) { return String(n).padStart(2, '0'); }
function formatDate(ts) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function formatTime(ts) {
  const d = new Date(ts);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
function formatDateTime(ts) { return `${formatDate(ts)} ${formatTime(ts)}`; }

function cleanFileName(s, maxLen) {
  if (!s) return '对话记录';
  return s.replace(/[<>:"/\\|?*\n\r]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, maxLen || 40) || '对话记录';
}

function extractText(entry) {
  if (!entry) return '';
  if (typeof entry === 'string') return entry;
  if (entry.text) return entry.text;
  if (Array.isArray(entry)) return entry.map(e => extractText(e)).join('\n');
  return '';
}

function kebabName(s) {
  return s.toLowerCase().replace(/[<>:"/\\|?*\n\r]/g, ' ').replace(/\s+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'untitled';
}

// ======== JSONL 解析 ========

function parseJSONL(filepath) {
  const raw = fs.readFileSync(filepath, 'utf8');
  const lines = raw.split('\n').filter(l => l.trim());
  const messages = [];

  for (const line of lines) {
    try {
      const entry = JSON.parse(line);
      if (entry.type === 'message') {
        const isToolCall = Array.isArray(entry.message.content) &&
          entry.message.content.some(c => c && c.type === 'toolCall');
        messages.push({
          id: entry.id,
          role: entry.message.role,
          content: entry.message.content,
          timestamp: entry.timestamp,
          isToolCall,
        });
      }
    } catch { /* skip */ }
  }

  return messages;
}

// ======== 知识点提取 ========
// 从 user→assistant 问答对中提取定义性/知识点内容

function extractKnowledge(messages) {
  const items = [];
  const seen = new Set();

  for (let i = 0; i < messages.length - 1; i++) {
    if (messages[i].role !== 'user') continue;
    if (messages[i + 1].role !== 'assistant') continue;

    const userText = extractText(messages[i].content).trim();
    const aiText = extractText(messages[i + 1].content).trim();

    if (!aiText || aiText.length < 20) continue;
    if (messages[i + 1].isToolCall) continue;

    // 跳过纯确认回复
    const skipPrefixes = ['好的', '收到', '让我', '我来', '请稍', '正在'];
    if (skipPrefixes.some(p => aiText.startsWith(p))) continue;

    const combined = userText + ' ' + aiText;
    const dedupKey = combined.replace(/\s+/g, '').slice(0, 80);
    if (seen.has(dedupKey)) continue;
    seen.add(dedupKey);

    // 宽松匹配：AI 回答中包含定义性/结论性内容
    const patterns = [
      /(.{6,40})(?:是|即为|就叫|指的是|表示)(.{5,})/,
      /(.{6,40})(?:功能|作用|用途)(?:为|是)?(.{5,})/,
      /(.{6,40})(?:配置|设置|参数)(?:为|是)?(.{5,})/,
      /(.{6,40})(?:位于|在)(.{5,})/,
      /(.{6,40})(?:需要|必须|应该)(.{5,50})/,
      /(.{6,40})(?:包含|包括|分为)(.{5,})/,
      /(.{6,40})(?:用于|用来)(.{5,})/,
    ];

    const matches = [];
    for (const p of patterns) {
      const m = aiText.match(p);
      if (m) matches.push(m[1].trim());
    }

    if (matches.length > 0) {
      // 取最长匹配作为标题
      matches.sort((a, b) => b.length - a.length);
      const title = cleanFileName(matches[0], 50);
      // 从 AI 回答中提取前 300 字作为知识正文
      const answer = aiText.slice(0, 500);

      items.push({
        title,
        answer,
        userQuestion: userText.slice(0, 120),
        timestamp: messages[i + 1].timestamp,
      });
    }
  }

  return items;
}

// ======== Markdown 渲染 ========

function roleIcon(role) {
  switch (role) {
    case 'user': return '👤 **瞿**';
    case 'assistant': return '🤖 **小艺**';
    default: return `⚙️ **${role}**`;
  }
}

function formatMessage(msg) {
  const icon = roleIcon(msg.role);
  const t = msg.timestamp ? ` (${formatDateTime(msg.timestamp)})` : '';

  let md = `### ${icon}${t}\n\n`;

  if (msg.isToolCall && Array.isArray(msg.content)) {
    const textParts = msg.content.filter(c => c.type === 'text').map(extractText).join('\n');
    if (textParts.trim()) md += textParts.trim() + '\n\n';

    for (const seg of msg.content) {
      if (seg.type !== 'toolCall') continue;
      md += `> \`🛠️ ${seg.name || 'tool'}\`\n`;
      if (seg.arguments) {
        try {
          const a = typeof seg.arguments === 'string' ? JSON.parse(seg.arguments) : seg.arguments;
          const show = {};
          for (const [k, v] of Object.entries(a)) {
            show[k] = String(v).length > 200 ? String(v).slice(0, 200) + '...' : v;
          }
          md += '> ' + JSON.stringify(show, null, 2).split('\n').join('\n> ') + '\n';
        } catch {
          md += '> ' + String(seg.arguments).split('\n').join('\n> ') + '\n';
        }
      }
      md += '\n';
    }
  } else {
    md += extractText(msg.content) + '\n\n';
  }

  return md;
}

// ======== 知识点卡片写入 ========

function writeKnowledgeCards(knowledgeItems, sessionLink) {
  if (knowledgeItems.length === 0) return 0;
  if (!fs.existsSync(KNOWLEDGE_DIR)) fs.mkdirSync(KNOWLEDGE_DIR, { recursive: true });

  const indexPath = path.join(KNOWLEDGE_DIR, '_index.md');
  let indexEntries = '';
  let count = 0;
  const seen = new Set();

  for (const item of knowledgeItems) {
    const key = kebabName(item.title);
    if (seen.has(key)) continue;
    seen.add(key);

    const kwFile = path.join(KNOWLEDGE_DIR, `${key}.md`);
    const date = item.timestamp ? formatDate(item.timestamp) : '';

    // 已有知识点卡片 → 追加反向链接
    if (fs.existsSync(kwFile)) {
      fs.appendFileSync(kwFile, `\n- 关联: [[${path.basename(sessionLink, '.md')}]] (${date || ''})\n`, 'utf8');
      count++;
      continue;
    }

    let card = '---\n';
    card += `title: "${item.title}"\n`;
    card += `date: ${date || 'unknown'}\n`;
    card += 'tags:\n  - knowledge\n  - auto-extracted\n';
    if (date) card += `  - ${date}\n`;
    card += '---\n\n';
    card += `# ${item.title}\n\n`;
    card += `> ${item.userQuestion}\n\n`;
    card += `${item.answer}\n\n`;
    card += '---\n\n';
    card += `## 来源\n\n- 会话: [[${path.basename(sessionLink, '.md')}]]\n`;
    if (date) card += `- 日期: ${date}\n`;

    fs.writeFileSync(kwFile, card, 'utf8');
    console.log(`  🧠 知识点: ${key}.md`);
    count++;

    const description = item.answer.replace(/\n/g, ' ').slice(0, 120);
    indexEntries += `- [[${key}|${item.title}]] — ${description}\n`;
  }

  if (indexEntries) {
    if (fs.existsSync(indexPath)) {
      fs.appendFileSync(indexPath, `\n## ${formatDate(Date.now())}\n\n${indexEntries}`);
    } else {
      const h = '---\ntitle: "知识索引"\ntags:\n  - knowledge\n  - index\n---\n\n# 知识索引\n\n自动从对话中提取的知识点。\n';
      fs.writeFileSync(indexPath, h + indexEntries, 'utf8');
    }
  }

  return count;
}

// ======== 主流程 ========

function main() {
  const args = process.argv.slice(2);
  const allMode = args.includes('--all');

  const metaPath = path.join(SESSIONS_DIR, 'sessions.json');
  if (!fs.existsSync(metaPath)) {
    console.error('❌ sessions.json 未找到');
    process.exit(1);
  }
  const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));

  // 获取会话文件列表
  const sessionFiles = [];
  if (allMode) {
    const seen = new Set();
    for (const [, m] of Object.entries(meta)) {
      if (m.sessionFile && fs.existsSync(m.sessionFile) &&
          m.sessionFile.endsWith('.jsonl') && !m.sessionFile.includes('.deleted.') && !m.sessionFile.includes('.reset.')) {
        if (seen.has(m.sessionFile)) continue;
        seen.add(m.sessionFile);
        sessionFiles.push(m.sessionFile);
      }
    }
    console.log(`📋 共 ${sessionFiles.length} 个会话`);
  } else {
    const current = meta['agent:main:main'];
    if (!current || !current.sessionFile) {
      console.error('❌ 未找到当前会话');
      process.exit(1);
    }
    sessionFiles.push(current.sessionFile);
    console.log(`📎 当前会话: ${path.basename(current.sessionFile)}`);
  }

  // 加载状态
  let state = {};
  try { if (fs.existsSync(STATE_FILE)) state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); } catch {}

  let totalNew = 0, totalKw = 0;

  for (const sf of sessionFiles) {
    if (!fs.existsSync(sf)) continue;
    const messages = parseJSONL(sf);
    if (messages.length === 0) continue;

    const sessionKey = path.basename(sf, '.jsonl');
    const lastId = state[sessionKey] || null;
    const lastIdx = lastId ? messages.findIndex(m => m.id === lastId) : -1;
    const newMessages = lastIdx >= 0 ? messages.slice(lastIdx + 1) : messages;
    if (newMessages.length === 0) continue;

    // 标题 & 目录
    const firstUser = messages.find(m => m.role === 'user');
    const title = cleanFileName(firstUser ? extractText(firstUser.content) : '对话记录');
    const date = formatDate(messages[0].timestamp);
    const outDir = path.join(OBSIDIAN_VAULT, date);
    if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

    const fileName = `${date}_${title}.md`;
    const filePath = path.join(outDir, fileName);
    const sessionRelPath = `${date}/${fileName}`;

    // 提取知识点
    const allKnowledge = extractKnowledge(messages);
    const newKnowledge = extractKnowledge(newMessages);

    // 构建 frontmatter
    const kwLinks = allKnowledge.slice(0, 15).map(k =>
      `  - "[[${kebabName(k.title)}|${cleanFileName(k.title, 50)}]]"`
    );

    const now = formatDateTime(Date.now());

    let md = '---\n';
    md += `title: "${title}"\n`;
    md += `date: ${date}\n`;
    md += `total_messages: ${messages.length}\n`;
    md += `new_messages: ${newMessages.length}\n`;
    md += `exported_at: "${now}"\n`;
    md += `knowledge_points: ${allKnowledge.length}\n`;
    md += 'tags:\n  - openclaw-session\n  - ai-chat\n';
    md += `  - ${date}\n`;
    md += 'links:\n' + kwLinks.join('\n') + '\n';
    md += '---\n\n';
    md += `# ${title}\n\n`;
    md += `> ${date} | 消息: ${messages.length} (+${newMessages.length})`;
    if (allKnowledge.length > 0) md += ` | 🧠 知识: ${allKnowledge.length}`;
    md += '\n\n';

    // 知识点摘要
    if (allKnowledge.length > 0) {
      md += '## 🧠 知识点\n\n';
      for (const kw of allKnowledge.slice(0, 20)) {
        const link = `[[${kebabName(kw.title)}|${cleanFileName(kw.title, 50)}]]`;
        md += `- ${link} — ${kw.userQuestion}\n`;
      }
      md += '\n---\n\n';
    }

    md += '## 对话\n\n';

    for (const msg of newMessages) {
      md += formatMessage(msg);
    }

    // 写入
    if (fs.existsSync(filePath) && lastIdx >= 0) {
      const append = md.split('\n## 对话\n\n').slice(1).join('\n## 对话\n\n');
      fs.appendFileSync(filePath, '\n\n---\n\n' + append, 'utf8');
      console.log(`  📄 +${newMessages.length}条 → ${fileName}`);
    } else {
      fs.writeFileSync(filePath, md, 'utf8');
      console.log(`  📄 ${fileName}`);
    }
    totalNew += newMessages.length;

    // 知识点卡片
    const kwCount = writeKnowledgeCards(newKnowledge, sessionRelPath);
    totalKw += kwCount;
    if (kwCount > 0) console.log(`  🧠 新增 ${kwCount} 个知识点`);
    else if (newKnowledge.length > 0) console.log(`  ⏭️  知识点已存在，更新反向链接`);

    // 更新状态
    state[sessionKey] = messages[messages.length - 1].id;
  }

  const stateDir = path.dirname(STATE_FILE);
  if (!fs.existsSync(stateDir)) fs.mkdirSync(stateDir, { recursive: true });
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8');

  console.log(`\n✅ 完成！${totalNew} 条消息, ${totalKw} 个新知识点`);
}

main();
