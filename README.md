# Damai Ticket Monitor

监控大麦网演唱会开票状态，开票时发送邮件 + 微信通知。

## 运行 schedule

Workflow 每天 **北京时间 09:00–20:00**（UTC 01:00–12:00）每 5 分钟触发一次。

- **7 月 20 日前**：每次触发执行一次检查（实际频率：每 5 分钟一次）
- **7 月 20–31 日**：每次触发进入轮询模式，持续 5 分钟每分钟检查一次（实际频率：每分钟一次）

时间窗口控制和轮询模式切换由 `main.py` 内部实现（`RUN_WINDOW_START`/`RUN_WINDOW_END` 和 `should_use_polling_mode`）。

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
