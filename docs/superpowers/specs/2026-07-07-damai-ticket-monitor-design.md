# 大麦网演唱会开票监控脚本设计文档

- 日期：2026-07-07
- 主题：刘宪华苏州演唱会开票监控
- 部署方式：GitHub Actions（公开仓库）+ Python
- 范围：监控 + 通知，不包含自动抢票

## 1. 项目目标

实现一个完全免费的自动化监控脚本：

1. 实时监控大麦网上「刘宪华 苏州 演唱会」的开票状态。
2. 7 月 20 日前每 5 分钟检查一次；7 月 20 日至 7 月 31 日每分钟检查一次。
3. 只在每天 9:00–20:00 之间运行。
4. 检测到状态从「未开售」变为「立即购买」时，立即发送邮件 + 微信通知。

## 2. 非目标

- 不实现自动登录、选座、下单、支付等抢票功能。
- 不保证 100% 实时，GitHub Actions 调度可能有分钟级延迟。
- 不长期维护通用大麦监控框架，仅针对本次演唱会。

## 3. 架构概览

```
GitHub Actions (cron 每 5 分钟)
        │
        ▼
Python 主控脚本 (main.py)
        │
        ├── 时间窗口判断 (9:00–20:00)
        ├── 日期模式选择 (单次检查 / 5 分钟轮询)
        ├── 调用 Damai 检查器
        │       ├── HttpDamaiChecker (默认)
        │       └── PlaywrightDamaiChecker (fallback)
        ├── 状态对比
        └── 触发通知
                ├── 邮件 (SMTP)
                └── 微信 (Server 酱 / PushPlus)
```

状态持久化通过仓库中的 `state.json` 实现，每次运行后由 GitHub Actions 自动提交。

## 4. 组件说明

### 4.1 GitHub Actions 工作流

文件：`.github/workflows/monitor.yml`

- 使用 `schedule` 触发器，每 5 分钟运行一次。
- 配置 `timeout-minutes: 10`，防止轮询死循环。
- 安装 Python 依赖并运行 `main.py`。
- 运行结束后，如果 `state.json` 发生变化，通过 `GITHUB_TOKEN` 自动提交。

### 4.2 主控脚本

文件：`main.py`

职责：

- 读取当前时间，判断是否处于 9:00–20:00，否则直接退出。
- 根据日期决定运行模式：
  - 7 月 20 日之前：执行一次检查。
  - 7 月 20 日及之后：循环 5 分钟，每分钟检查一次。
- 调用检查器、对比状态、触发通知、保存状态。

### 4.3 大麦检查器

目录：`checkers/`

抽象接口 `DamaiChecker`，统一返回结构：

```json
{
  "title": "刘宪华演唱会-苏州站",
  "url": "https://detail.damai.cn/...",
  "status": "on_sale",
  "on_sale": true,
  "checked_at": "2026-07-07T10:00:00+08:00"
}
```

实现：

- `HttpDamaiChecker`：使用 `requests` 访问大麦搜索页和详情页，解析 HTML。
- `PlaywrightDamaiChecker`：当 HTTP 方式被反爬拦截时启用，模拟真实浏览器行为。

搜索逻辑：

- 关键词：「刘宪华 苏州 演唱会」。
- 解析搜索结果，按城市和演出名称匹配最相似的一条。
- 进入详情页后读取购票按钮文本，如「立即购买」表示已开票。

### 4.4 通知器

目录：`notifiers/`

- `email.py`：通过 SMTP 发送邮件通知。
- `wechat.py`：通过 Server 酱或 PushPlus HTTP API 发送微信消息。

通知策略：

- 仅在状态从 `not_on_sale` 变为 `on_sale` 时发送。
- 邮件和微信独立发送，互不影响。
- 连续多次相同状态不重复通知。

### 4.5 状态管理

文件：`state.py` + `state.json`

- `state.json` 保存上一次检查的状态。
- 每次运行前读取，运行后写入并提交。
- 用于去重，避免重复通知。

示例：

```json
{
  "last_status": "on_sale",
  "last_title": "刘宪华演唱会-苏州站",
  "last_url": "https://detail.damai.cn/...",
  "last_checked_at": "2026-07-07T10:00:00+08:00",
  "notified": true
}
```

### 4.6 配置

所有敏感配置通过 GitHub Secrets 注入为环境变量：

| 环境变量 | 说明 |
| --- | --- |
| `CONCERT_KEYWORD` | 搜索关键词，默认「刘宪华 苏州 演唱会」 |
| `SMTP_HOST` | SMTP 服务器地址 |
| `SMTP_PORT` | SMTP 端口 |
| `SMTP_USER` | 发件邮箱 |
| `SMTP_PASSWORD` | 发件邮箱密码/授权码 |
| `EMAIL_TO` | 收件人邮箱 |
| `WECHAT_TOKEN` | Server 酱 SCKEY 或 PushPlus Token |
| `WECHAT_PROVIDER` | `serverchan` 或 `pushplus` |

## 5. 数据流

一次 GitHub Actions 运行的完整流程：

1. cron 每 5 分钟触发 workflow。
2. 读取 `state.json` 获取上一次状态。
3. 判断当前时间是否在 9:00–20:00，否则退出。
4. 根据日期选择运行模式。
5. 调用检查器搜索大麦并读取售票状态。
6. 将新状态与 `state.json` 对比。
7. 如果变为「立即购买」，发送邮件和微信通知。
8. 更新 `state.json` 并提交到仓库。

状态转换：

```
未开售 → 立即购买 → 发通知 → 已通知
```

后续检查若状态保持「立即购买」，不再重复通知。

## 6. 错误处理

### 6.1 网络异常

- `requests` 设置 10 秒超时。
- 失败时重试 3 次，使用指数退避。
- 单次失败不终止运行，记录日志后继续。

### 6.2 反爬/拦截

- 携带常见浏览器 User-Agent。
- 识别反爬特征：HTTP 403/429、验证码页面、页面结构异常。
- 触发 Playwright fallback。
- 如果 fallback 也失败，发送「检查器失效，请人工查看」通知。

### 6.3 搜索结果异常

- 搜索结果为空：记录日志，不发送通知。
- 多条结果：按城市+艺术家名取最相似一条。
- 匹配不确定：发送一次「发现疑似演出，请确认」通知。

### 6.4 通知发送失败

- 邮件和微信独立发送，失败互不影响。
- 失败时记录日志，下次运行重试。
- 连续失败超过阈值时，发送备用告警（如果邮件通道仍可用）。

### 6.5 GitHub Actions 环境异常

- workflow 设置 10 分钟超时。
- 运行失败时 GitHub 会默认邮件提醒仓库所有者。
- `state.json` 写入失败不阻塞通知发送。

## 7. 测试方案

### 7.1 单元测试

- 使用 `pytest`。
- 状态管理：验证状态变化才发通知，重复状态不发。
- 检查器：用本地 HTML fixture 模拟大麦页面，验证状态解析。
- 通知器：用 mock 验证 SMTP 和 Server 酱 API 调用参数正确。

### 7.2 集成测试

- 本地执行 `python main.py --dry-run`，观察日志。
- 配置测试环境变量，发送一条测试邮件和微信消息。

### 7.3 GitHub Actions 测试

- 临时将 cron 调整为 5 分钟一次，观察运行日志。
- 验证 `state.json` 是否正确提交。
- 验证非运行时间段是否正确跳过。

### 7.4 真实演练

- 找一个已开票的演出，验证「立即购买」状态能正确识别。
- 手动修改 `state.json` 触发通知，验证双通道可达。

### 7.5 Fallback 测试

- 模拟 HTTP 检查器被封，验证 Playwright 能接管。
- 模拟通知通道失败，验证运行不崩溃。

## 8. 部署说明

1. 在 GitHub 创建**公开仓库**。
2. 将代码推送到 `main` 分支。
3. 在 Settings → Secrets and variables → Actions 中配置环境变量。
4. 启用 GitHub Actions 工作流。
5. 观察前几次运行日志，确认正常。

## 9. 限制与风险

- GitHub Actions 调度不保证精确到秒，实际间隔可能略有波动。
- 大麦网页面结构或反爬策略变化时，检查器可能需要更新。
- 公开仓库会暴露代码，但不会暴露 GitHub Secrets。
- 该脚本仅用于个人监控，不保证一定能抢到票。

## 10. 未来扩展（可选）

- 支持多个演出同时监控。
- 增加短信通知通道。
- 增加已售罄状态的识别与通知。
- 将状态持久化从 `state.json` 迁移到数据库或 KV 存储。
