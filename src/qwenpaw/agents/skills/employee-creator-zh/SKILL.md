---
name: employee-creator
description: "当用户希望创建新的 AgentDesk 数字员工（岗位智能体）时使用。触发表达包括「帮我创建一个 XXX 专家」「添加员工」「招募岗位智能体」「新建数字员工」以及 AgentDesk「添加员工」入口预填的创建模板。"
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    icon: "idcard"
---

# 创建数字员工（AgentDesk 岗位智能体）

帮用户在 AgentDesk 中创建一名新的**岗位智能体**（数字员工），并加入员工列表。

## 引导流程归属（重要）

- **本技能承担全部「添加员工」引导**：收集名称、职责、可选技能，并在用户确认后调用 API 落地。
- **不要**对 default 代理或新创建的员工触发 `BOOTSTRAP.md` / 首次引导问卷；创建流程就在本技能对话中完成。
- `POST /api/plaza/<name>/join` 会预填员工 `PROFILE.md`、移除 `BOOTSTRAP.md`、写入 `EMPLOYEE.json` 并标记 `.bootstrap_completed`。
- 创建完成后，该员工可直接接受派发任务与普通对话（如「你好」），**无需**再次走引导。

## 执行规则

- 跳过 `create_plan`、多步问卷与 `BOOTSTRAP.md` 引导。
- 用户消息已包含名称、职责且无占位符（如 `XXX`、`[请补充…]`）时，**直接调用 API**，无需二次确认。
- 不做端口探测、后端拉起、环境二次发现；优先使用已知 API 基址，默认 `http://127.0.0.1:8088/api`。
- 不要访问前端 HTML 路由；只调用 AgentDesk API（`/api/plaza`、`/api/plaza/<name>/join`、`/api/skills/...`）。
- 避免全量技能列表大输出；只有技能名不明确时，调用一次 `GET /api/skills` 做精确匹配。
- API 成功前不要声称已创建；失败时返回具体错误与修复建议。

## 何时使用

- 用户要「添加员工」「创建专家」「招募岗位智能体」
- 用户已填写创建模板（专家名称、擅长领域、经验背景等）
- 用户描述一名新员工的职责，希望系统落地为可派发的 agent

## 不要用于

- 仅修改已有员工描述 → 用 `PUT /api/plaza/{name}` 或 `PUT /api/employees/{name}`
- 创建 QwenPaw 底层 agent 但不进 AgentDesk 广场 → 用 `POST /api/agents`（CLI：`qwenpaw agents create`）
- 创建 skill 本身 → 使用 `make-skill` 技能

## 工作流

### 1. 收集信息

从用户消息中提取或追问：

| 字段 | 必填 | 说明 |
|------|------|------|
| **name** | 是 | 员工显示名称，如「销售助理」「数据分析师」 |
| **desc** | 是 | 职责与能力描述，会写入岗位卡片并同步到 agent `description` / `PROFILE.md` |
| **tags** | 否 | 标签列表，默认 `["AgentDesk"]` |
| **avatar** | 否 | 头像 URL（留空则自动生成人像） |
| **skills** | 否 | 建议挂载的技能名列表（pool 中已有） |

若模板里仍有 `XXX`、`XXXXX` 或 `[请补充…]` 占位，先请用户补全，**不要**用占位符创建。

### 2. 调用 AgentDesk API 创建

**创建 1 名员工时优先使用 `create_agentdesk_employee` 工具**（一次调用完成 plaza + join，自动处理 JSON 与中文 URL）。
**创建多名员工时必须优先使用 `create_agentdesk_employees` 工具**，把所有员工作为数组一次传入；不要并发调用多个 `create_agentdesk_employee`，否则多个 agent provisioning / 技能挂载会抢占本地配置与 workspace 文件，容易超时。
**不要**用 `execute_shell_command` 执行 curl / Invoke-WebRequest — Windows PowerShell 下 JSON 转义极易失败。

仅在工具不可用时才考虑 shell；API 基址默认 `http://127.0.0.1:8088/api`。

**步骤 A — 创建岗位卡片**（由 `create_agentdesk_employee` 内部完成）

```http
POST /api/plaza
Content-Type: application/json

{
  "name": "<员工名称>",
  "desc": "<职责描述>",
  "avatar": "🤖",
  "tags": ["AgentDesk"],
  "skills": ["make_plan", "docx"]
}
```

**步骤 B — 加入员工列表并创建底层 agent**（同上，工具自动调用）

```http
POST /api/plaza/<url-encoded-name>/join
```

`join` 会写入 employees 存储、调用 `ensure_employee_agent_profile` 创建/同步 QwenPaw agent 与工作区，并根据 plaza 的 `skills` 同步安装技能（跳过 BOOTSTRAP）。

### 3. 技能绑定策略（确定性）

根据专长**自动推荐**技能（用户未指定时）：

| 专长关键词 | 建议技能 |
|-----------|---------|
| 文档、Word、报告 | `docx`, `make_plan` |
| 表格、Excel、数据 | `xlsx`, `make_plan` |
| PPT、演示 | `pptx`, `make_plan` |
| 规划、方案、SOP | `make_plan`, `docx` |
| 消息、通知 | `channel_message`, `make_plan` |
| 舆情、新闻 | `news`, `file_reader` |
| 默认 | `make_plan`, `file_reader` |

优先把技能放进 `POST /api/plaza` 的 `skills` 字段并依赖 `join` 一次性完成绑定。  
`join` 成功且返回 `joined: true` 时，默认视为绑定完成，**不要**逐个 `mount`。

仅在 `join` 返回了明确的失败技能（例如 `failed_skills`）时，对失败项做补偿挂载：

```http
POST /api/skills/<skill_name>/mount
Content-Type: application/json

{ "employee_name": "<员工名称>" }
```

补偿挂载时，`<skill_name>` 使用技能标识；后端会解析别名并对已安装技能幂等返回成功。

### 4. 收尾（一次确认）

- 仅做一次最终确认（优先使用 join 返回；必要时单次 `GET /api/employees`）
- 告知员工已创建，可在「团队 → 员工列表」或「岗位智能体」中查看
- 说明如何「派发任务」给该员工
- 若 API 失败，返回错误详情并给出修复建议（重名、非法字符等）

## 描述撰写建议

`desc` 应清晰说明：

- 专长领域与典型任务类型
- 输出风格或约束
- 多 agent 协作时其他 agent 会读此描述来决定是否委派

## 示例

用户：「帮我创建一个舆情分析专家，擅长监测社媒与撰写日报。经验：5 年 PR。」

1. 确认名称「舆情分析专家」与职责摘要
2. `POST /api/plaza`（含 `skills: ["news","file_reader","make_plan"]`）+ `POST /api/plaza/舆情分析专家/join`
3. 若 join 报告失败技能，仅对失败项调用 mount API
4. 回复创建成功、已绑定技能与下一步操作
