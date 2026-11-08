# download-reports.cjs

## 文件头注释

```cjs
/**
 * Email report downloader - manual scan with local filtering
 * Workaround for qiye.163.com IMAP SEARCH not supporting FROM/SUBJECT Chinese queries
 */
```

## attachmentOnly 模式注释

```cjs
// subject may be modified → match by attachment name only
```

```cjs
// attachmentOnly mode: after sender match, fetch full email to check attachment name; stop after MAX_FULL_FETCH candidates
```

## 匹配规则说明

```cjs
const rule = byAtt
  ? '发件人含 "'+report.sender+'" 且附件名含"'+report.fileFilter+'"（不卡主题）'
  : '发件人含 "'+report.sender+'" 且主题含"'+report.keyword+'"';
```

## 提示信息

```cjs
console.log('   ⚠️ 已检查'+MAX_FULL_FETCH+'封候选邮件仍无匹配附件，停止往前扫');
```

```cjs
console.log('   ⏭️ #'+i+' 主题「'+subject.slice(0,40)+'」无匹配附件，继续往前找');
```
