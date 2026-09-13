# v2free-checkin

自动登录 [v2free](https://w1.v2free.cyou/auth/login) 并执行签到的 Edge 浏览器自动化脚本。

## 依赖

```powershell
pip install selenium
```

需要 Microsoft Edge 及对应版本的 [Edge WebDriver](https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/)。确保 `msedgedriver` 在 PATH 中，或放置于脚本同目录。

## 使用方法

```powershell
python checkin.py
```

### 凭据配置（三选一）

| 方式 | 说明 |
|------|------|
| **交互式保存** | 首次运行按提示输入账号密码，选择保存到 `cred.json`（base64 编码，非明文） |
| **环境变量** | 设置 `V2FREE_ACCOUNT` 和 `V2FREE_PASSWORD` 后运行 |
| **手动创建 cred.json** | 格式见下方 |

cred.json 格式（value 为 base64 编码后的字符串）：

```json
{
  "account": "cmx1eXR3...",
  "password": "MTIzNDU2Nzg4..."
}
```

## 功能

- 自动探测页面登录表单元素（智能匹配 email/password 输入框）
- 凭据仅以 base64 编码存储，源码不出现明文密码
- 登录完成后浏览器保持打开，按 Enter 关闭
