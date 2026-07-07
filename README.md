# Damai Ticket Monitor

监控大麦网演唱会开票状态，开票时发送邮件 + 微信通知。

## 配置

在 GitHub 仓库 Settings → Secrets and variables → Actions 中设置以下 Secrets：

| Secret | 说明 |
| --- | --- |
| CONCERT_KEYWORD | 搜索关键词，默认：刘宪华 苏州 演唱会 |
| SMTP_HOST | SMTP 服务器 |
| SMTP_PORT | SMTP 端口 |
| SMTP_USER | 发件邮箱 |
| SMTP_PASSWORD | 邮箱授权码 |
| EMAIL_TO | 收件邮箱 |
| WECHAT_TOKEN | Server 酱 SCKEY 或 PushPlus token |
| WECHAT_PROVIDER | serverchan 或 pushplus |

## 本地测试

```bash
pip install -r requirements-dev.txt
pytest
```
