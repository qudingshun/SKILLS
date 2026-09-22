#!/usr/bin/env node
/**
 * Pre-commit secret scanner.
 *
 * Scans the content that is about to be committed (the git index) and blocks
 * the commit when it finds hardcoded credentials such as
 *   pass:'#a2uCpEAxXwJderr'
 *   PASSWORD = "Scm123456"
 *   api_key: "sk-..."
 *   -----BEGIN PRIVATE KEY-----
 *
 * Usage:
 *   node .githooks/scan-staged.mjs          # scan staged changes (used by the hook)
 *   SCAN_ALL=1 node .githooks/scan-staged.mjs   # scan every tracked file (for tuning)
 *
 * Bypass a false positive with:  git commit --no-verify
 */

import { execFileSync } from 'node:child_process';

const SCAN_ALL = process.env.SCAN_ALL === '1';
const MAX_BYTES = 1_000_000;

const SKIP_PATHS = [
  /(^|\/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|npm-shrinkwrap\.json)$/i,
  /(^|\/)(node_modules|\.venv|venv)\//,
  /\.min\.(js|css)$/i,
  /(^|\/)\.githooks\//,
  /\.(png|jpe?g|gif|ico|bmp|pdf|zip|gz|7z|rar|xlsx?|docx?|pptx?|dat|woff2?|ttf|eot|mp4|mov|sqlite|db)$/i,
];

const BAD_FILENAME = /(^|\/)(\.env(\.[^/]+)?|cred\.json|credentials(\.json)?|id_rsa|id_dsa|.*\.(pem|p12|pfx|key|keystore|jks))$/i;
const SAFE_FILENAME = /\.(example|sample|template|dist)$/i;

const ALLOW_VALUE = [
  /^\*+$/,
  /^x+$/i,
  /^<[^<>]+>$/,
  /^\{[^{}]+\}$/,
  /^\[[^[\]]+\]$/,
  /\.\.\./,
  /^\*+REMOVED\*+$/i,
  /^(your|my|the|new|old|test|testing|example|sample|placeholder|dummy|fake|changeme|change_me|redacted|removed|todo|fixme|none|null|undefined|nil|true|false|password|passwd|secret|token|key|value|empty|blank)\b/i,
  /(env|environ|getenv|process\.env|os\.environ|\$\{|\$\(|%[A-Z0-9_]+%)/i,
];

const RULES = [
  {
    name: 'hardcoded credential assignment',
    valueGroup: 3,
    re: /(?<![A-Za-z0-9_])(password|passwd|pwd|pass|secret|token|api[_-]?key|apikey|access[_-]?key|auth[_-]?token|client[_-]?secret|credential)s?\s*[:=]\s*(['"`])([^'"`\r\n]{6,})\2/gi,
  },
  {
    name: 'hardcoded env fallback (|| or ??)',
    valueGroup: 3,
    re: /process\.env\.[A-Za-z0-9_]+(\[[^\]]+\])?\s*(?:\|\||\?\?)\s*(['"`])([^'"`\r\n]{6,})\2/g,
  },
  {
    name: 'hardcoded env fallback (default arg)',
    valueGroup: 2,
    re: /(?:process\.env|os\.environ|os\.getenv|getenv)\s*(?:\.get)?\s*\([^)\r\n]*?,\s*(['"`])([^'"`\r\n]{6,})\1/g,
  },
  {
    name: 'hardcoded env fallback (or)',
    valueGroup: 2,
    re: /os\.environ(?:\.get)?\([^)\r\n]*\)\s*or\s*(['"`])([^'"`\r\n]{6,})\1/g,
  },
  {
    name: 'private key block',
    valueGroup: null,
    re: /-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----/g,
  },
];

function listFiles() {
  const args = SCAN_ALL
    ? ['ls-files', '-z']
    : ['diff', '--cached', '--name-only', '--diff-filter=ACM', '-z'];
  return execFileSync('git', args, { maxBuffer: 256 * 1024 * 1024 })
    .toString('utf8')
    .split('\0')
    .filter(Boolean);
}

function readIndex(file) {
  try {
    const buf = execFileSync('git', ['show', ':' + file], { maxBuffer: 256 * 1024 * 1024 });
    if (buf.includes(0) || buf.length > MAX_BYTES) return null;
    return buf.toString('utf8');
  } catch {
    return null;
  }
}

function isAllowedValue(value) {
  const v = value.trim();
  if (v.length < 6) return true;
  return ALLOW_VALUE.some((re) => re.test(v));
}

function redact(text, value) {
  if (!value) return text;
  return text.split(value).join('***');
}

function scanFile(file, text) {
  const findings = [];
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    for (const rule of RULES) {
      rule.re.lastIndex = 0;
      let m;
      while ((m = rule.re.exec(line)) !== null) {
        const value = rule.valueGroup == null ? null : m[rule.valueGroup];
        if (value != null && isAllowedValue(value)) continue;
        findings.push({
          file,
          line: i + 1,
          rule: rule.name,
          text: redact(line.trim(), value).slice(0, 200),
        });
        break;
      }
    }
  }
  return findings;
}

function main() {
  const files = listFiles();
  const findings = [];

  for (const file of files) {
    if (SKIP_PATHS.some((re) => re.test(file))) continue;
    if (BAD_FILENAME.test(file) && !SAFE_FILENAME.test(file)) {
      findings.push({ file, line: 0, rule: 'sensitive file name', text: '(whole file blocked)' });
      continue;
    }
    const text = readIndex(file);
    if (text == null) continue;
    findings.push(...scanFile(file, text));
  }

  if (findings.length === 0) return 0;

  console.error('\n[secret-scan] 提交被阻止：检测到疑似明文凭据\n');
  for (const f of findings) {
    const loc = f.line > 0 ? `${f.file}:${f.line}` : f.file;
    console.error(`  ${loc}  [${f.rule}]`);
    if (f.text) console.error(`      ${f.text}`);
  }
  console.error('\n请移除明文，改用环境变量/加密配置；确实为误报可用: git commit --no-verify\n');
  return 1;
}

process.exit(main());
