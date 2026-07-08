# Damai Ticket Monitor

监控大麦网演唱会开票状态，开票时发送邮件 + 微信通知。

> 仅读取开票状态，**不自动购票**。

## 运行 schedule

Workflow 每天 **北京时间 09:00–20:00** 每 5 分钟触发一次。最后一个触发是
19:55 CST（11:55 UTC）；20:00 之后的运行会被 `main.py` 的运行窗口跳过，因此
提前一小时停止以避免浪费 Action 分钟（cron 范围 `1-11` UTC）。

- **7 月 20 日前**：每次触发执行一次检查（实际频率：每 5 分钟一次）
- **7 月 20–31 日**：每次触发进入轮询模式，持续 5 分钟每分钟检查一次（实际频率：每分钟一次）

时间窗口控制和轮询模式切换由 `main.py` 内部实现（`RUN_WINDOW_START`/`RUN_WINDOW_END`、`POLL_SWITCH_DATE`/`POLL_END_DATE` 和 `should_use_polling_mode`）。

## 项目结构

| 模块 | 职责 |
| --- | --- |
| `main.py` | 入口、运行窗口/轮询切换、`run_once` 端到端流程 |
| `config.py` | 从环境变量加载 `Config` |
| `state.py` | `State` 持久化与 `should_notify` 去重判断 |
| `checkers/http.py` | `HttpDamaiChecker`（requests 方案） |
| `checkers/playwright.py` | `PlaywrightDamaiChecker`（浏览器 fallback） |
| `checkers/base.py` | `ConcertResult` 数据类与 `DamaiChecker` 协议 |
| `notifiers/email.py` | `EmailNotifier`（SMTP） |
| `notifiers/wechat.py` | `WeChatNotifier`（Server 酱 / PushPlus） |
| `.github/workflows/monitor.yml` | 定时触发并回写 `state.json` |

HTTP checker 优先；当大麦返回反爬/CAPTCHA 页面时，自动回退到 Playwright 浏览器 checker。

## 配置

在 GitHub 仓库 Settings → Secrets and variables → Actions 中设置以下 Secrets：

| Secret | 说明 |
| --- | --- |
| CONCERT_KEYWORD | 搜索关键词，默认：刘宪华 苏州 演唱会 |
| CONCERT_DETAIL_URL | 指定详情页 URL（可选），设置后跳过搜索直接检查该页面，无「预售」即认为在售 |
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
pytest -v
```

测试覆盖：配置加载、状态读写与去重、HTTP checker 解析、邮件/微信通知、
运行窗口与轮询切换，以及 `run_once` 端到端集成校验（含重复抑制）。
