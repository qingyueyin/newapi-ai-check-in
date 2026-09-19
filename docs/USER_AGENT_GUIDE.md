# User-Agent 配置功能指南

本文档详细介绍了为每个账号配置自定义 User-Agent 的功能。

---

## 快速开始

### 1. 通过 Web 界面配置（推荐）

```bash
uv run python web_config.py
```

浏览器会自动打开 `http://127.0.0.1:8790`

在账号编辑表单中，找到 **User-Agent** 字段：

```
┌──────────────────────────────────────────────────────────────────┐
│ User-Agent (可选，留空使用浏览器自动获取)                         │
│ ┌────────────────────────────────────────────────────────────┐   │
│ │ Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/...  │   │
│ └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**配置方式：**
- **留空** = 使用浏览器自动获取的 UA（默认）
- **填写** = 使用自定义 UA 字符串

### 2. 手动编辑 accounts.json

在账号配置中添加 `user_agent` 字段：

```json
{
  "name": "测试账号",
  "provider": "anyrouter",
  "api_user": "123456",
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "cookies": {
    "session": "your_session_cookie"
  }
}
```

---

## 功能特性

### ✅ 完全可选
- 未配置 `user_agent` 时，使用浏览器自动获取的 UA
- 只有需要的账号才配置，其他账号不受影响
- 向后兼容，现有配置无需修改

### ✅ 智能 Client Hints 生成
当提供自定义 UA 时，系统会：
- 自动检测浏览器类型（Chrome/Edge/Firefox/Safari）
- 为 Chrome/Edge 自动生成匹配的 `sec-ch-ua` 系列 Headers
- 从 UA 字符串中智能解析平台、版本、架构信息
- Firefox UA 不生成 Client Hints（符合浏览器行为）

**自动生成的 Client Hints 示例（Chrome）：**

```python
{
    'sec-ch-ua': '"Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua-platform-version': '"15.0.0"',
    'sec-ch-ua-arch': '"x86"',
    'sec-ch-ua-bitness': '"64"',
    'sec-ch-ua-model': '""',
    'sec-ch-ua-full-version-list': '"Chromium";v="131.0.6778.86", "Not_A Brand";v="24.0.0.0"'
}
```

### ✅ 全流程覆盖
自定义 UA 会应用到所有请求：
- ✅ Cloudflare 验证
- ✅ Linux.do OAuth 登录
- ✅ GitHub OAuth 登录
- ✅ 所有签到请求
- ✅ CDK 获取请求

---

## 常用 User-Agent 示例

### Chrome (Windows)
```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
```

### Chrome (macOS)
```
Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
```

### Firefox (Windows)
```
Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0
```

### Firefox (macOS)
```
Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0
```

### Edge (Windows)
```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0
```

---

## 适用场景

### ✅ 需要配置的情况

1. **Cloudflare 拦截**
   - 某个账号总是被 Cloudflare 挑战
   - 默认 UA 无法通过验证

2. **特定站点要求**
   - 站点只接受特定浏览器
   - 需要模拟特定设备或系统

3. **多账号隔离**
   - 不同账号使用不同 UA
   - 降低账号关联风险

### ❌ 不需要配置的情况

- 签到正常工作
- 没有被拦截
- 不确定（先不配置，有问题再说）

---

## 运行效果

### 配置了 UA 的账号

```bash
$ uv run python main.py

账号: 薄荷
ℹ️ 使用自定义 User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)...
正在获取 Cloudflare Clearance...
✓ Cloudflare 验证通过
✓ 签到成功！今日获得 1 积分
```

### 没配置 UA 的账号

```bash
$ uv run python main.py

账号: 薄荷
正在获取 Cloudflare Clearance...
✓ Cloudflare 验证通过
✓ 签到成功！今日获得 1 积分
```

---

## 技术实现

### 修改的文件

1. **配置解析** (`utils/config.py`)
   - `AccountConfig` 类添加 `user_agent: str | None = None` 字段
   - `from_dict` 方法解析并传递配置

2. **Headers 生成** (`utils/get_headers.py`)
   - `get_browser_headers` 函数支持自定义 UA
   - 智能生成 Client Hints
   - 浏览器类型识别

3. **Cloudflare 验证** (`utils/get_cf_clearance.py`)
   - 传递自定义 UA 到浏览器请求

4. **OAuth 登录** (`sign_in_with_linuxdo.py`, `sign_in_with_github.py`)
   - 两处 Cloudflare 检测点读取并传递自定义 UA

5. **签到流程** (`checkin.py`, `utils/get_cdk.py`)
   - 统一使用自定义 UA

6. **Web 界面** (`web_config.py`) ⭐
   - HTML 表单新增 UA 输入字段
   - JavaScript 读取和保存逻辑

---

## 注意事项

### 1. UA 格式
- 必须是有效的 User-Agent 字符串格式
- 建议使用真实浏览器的 UA

### 2. Client Hints
- 系统会自动生成，无需手动配置
- 如果 UA 格式不标准，可能无法正确生成

### 3. 留空行为
- 留空时使用浏览器自动获取的 UA
- 不影响现有功能

### 4. 浏览器支持
- Chrome/Edge：完整 Client Hints 支持
- Firefox：基础 Headers，无 Client Hints
- Safari：基础 Headers

---

## 故障排除

### 问题：配置了 UA 但没生效
- 检查 `accounts.json` 中 `user_agent` 字段格式是否正确
- 确认已保存配置并重新运行签到
- 查看运行日志中是否有 "ℹ️ 使用自定义 User-Agent" 提示

### 问题：Cloudflare 仍然拦截
- 尝试更换不同的 UA 字符串
- 确认 UA 格式完整且真实
- 检查是否需要配合代理使用
- 考虑使用不同浏览器的 UA

### 问题：Web 界面看不到 UA 字段
- 确认使用最新版本的 `web_config.py`
- 刷新浏览器页面（Ctrl+F5）
- 检查浏览器控制台是否有错误

---

## 相关文档

- [README.md](README.md) - 完整配置文档
- [USER_AGENT_CONFIG.md](USER_AGENT_CONFIG.md) - 详细使用指南
- [UA_FEATURE_SUMMARY.md](UA_FEATURE_SUMMARY.md) - 功能实现总结
- [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md) - 技术实现报告

---

## 快速参考

**启动 Web 配置：**
```bash
uv run python web_config.py
```

**配置 User-Agent：**
编辑账号 → User-Agent 字段 → 保存

**运行签到：**
```bash
uv run python main.py
```

---

**最后更新**: 2026-09-19  
**功能状态**: ✅ 已完成
