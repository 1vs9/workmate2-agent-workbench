# AgentDesk2

AgentDesk2 是一个基于 [QwenPaw](https://github.com/agentscope-ai/QwenPaw) 的本地优先 AI Agent 工作台。

这个仓库的目标不是做一个普通聊天框，而是展示一个更接近真实产品的 agentic workbench：任务对话、数字员工、团队协作、技能挂载、流式事件、执行过程可视化、长任务恢复、产物文件管理和本地数据运行。

我把它开源出来，主要用于展示我在 AI coding 和 agent 系统方向的工程能力：不只会调用模型 API，也关注 agent runtime 和产品层之间的边界、状态机、可恢复流式交互、多智能体编排、测试和部署体验。

## 项目亮点

| 方向 | 体现 |
| --- | --- |
| Agent 产品架构 | 在 QwenPaw runtime 之上构建 AgentDesk 产品 BFF 和 React 前端 |
| 多智能体协作 | 支持 Leader / Member 团队会话、成员标签页、派工事件和 timeline |
| 流式事件系统 | 统一 SSE 协议，前端用 reducer 收敛增量消息、工具调用和 trace |
| 长任务可靠性 | 处理 reconnect、stale run、断线后 finalization、迟到事件和状态回写 |
| 技能系统 | 支持本地技能库、市场技能、员工绑定技能和对话级临时挂载 |
| 本地优先 | 任务、session、workspace、产物文件默认运行在用户本地环境 |
| 工程化 | 包含后端单测、前端测试、e2e 脚手架、架构文档和部署脚本 |

## 适合看什么

如果你是从招聘、兼职合作或技术评估角度看这个项目，建议优先看：

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：AgentDesk 前端、BFF 和 QwenPaw runtime 的边界。
- [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md)：task/session 映射、团队编排、流式事件和技能挂载。
- [docs/CASE_STUDY_STALE_TEAM_RUNS.md](docs/CASE_STUDY_STALE_TEAM_RUNS.md)：一个真实可靠性问题的分析，团队任务卡在 `running` 时如何修。
- [docs/PORTFOLIO_NOTES.md](docs/PORTFOLIO_NOTES.md)：这个项目对外展示时的技术重点。
- `src/qwenpaw/agentdesk/`：AgentDesk 产品层后端。
- `src/qwenpaw/agentdesk/web/`：AgentDesk React 前端。
- `tests/unit/agentdesk/` 和 `tests/agentdesk/`：AgentDesk 相关回归测试。

## 功能概览

- 首页任务对话：创建任务、发送消息、查看流式回复。
- 执行过程面板：展示工具调用、命令输出、深度思考和 trace。
- 数字员工：创建、配置、切换不同 agent profile。
- 团队模式：由队长 agent 规划和派工，成员 agent 独立执行。
- 成员标签页：Leader 主会话和各成员会话分区展示，避免串流。
- 技能挂载：从技能池或市场安装技能，并挂载到指定员工或对话。
- 自动化任务：AgentDesk job 与 QwenPaw cron 能力桥接。
- 产物管理：PPT、PDF、代码等文件写入 agent workspace，并通过任务 API 预览。
- 本地配置：模型 Provider、API Key、数据目录、MCP 等配置在本地维护。

## 快速启动

### 环境要求

| 依赖 | 说明 |
| --- | --- |
| Python >= 3.11 | 后端运行时 |
| Node.js + npm | AgentDesk 前端构建 |
| Git | 克隆仓库 |

### 安装运行

```bash
git clone https://github.com/1vs9/agentdesk2.git
cd agentdesk2
pip install -e .
agentdesk app
```

`pip install -e .` 会注册两个命令：

- `agentdesk`：AgentDesk 兼容入口。
- `qwenpaw`：QwenPaw 原生命令。

说明：为了不破坏现有部署和测试，内部 Python 包路径、数据目录和 CLI 仍保留历史兼容名 `agentdesk`；对外项目名统一使用 AgentDesk2。

首次执行 `agentdesk app` 时，会检查前端构建产物是否存在。如果 `src/qwenpaw/agentdesk/static_next/` 缺失或过期，会自动进入 `src/qwenpaw/agentdesk/web/` 执行：

```bash
npm ci
npm run build
```

启动完成后访问：

```text
http://127.0.0.1:8088
```

左下角用户头像进入配置页，可以设置模型 Provider、API Key 和数据目录。

### 手动构建前端

如果自动构建失败，或者你想提前构建：

```bash
cd src/qwenpaw/agentdesk/web
npm ci
npm run build
cd ../../../../..
agentdesk app
```

### 前端开发模式

```bash
# 终端 1
agentdesk app

# 终端 2
cd src/qwenpaw/agentdesk/web
npm install
npm run dev
```

然后访问：

```text
http://localhost:5174
```

### 停止服务

```bash
agentdesk kill
agentdesk kill --port 8088
```

## 系统架构

AgentDesk2 的核心设计是：AgentDesk 负责产品语义，QwenPaw 负责 agent runtime。

```text
React AgentDesk 前端
  - TaskChat
  - team tabs
  - stream reducer
  - trace panel
  - artifact preview
        |
        | REST + SSE
        v
AgentDesk BFF
  - task metadata
  - stream translation
  - team orchestration
  - skill mounting
  - persistence
  - artifact indexing
        |
        | runtime adapter
        v
QwenPaw Runtime
  - agent run
  - tools
  - sessions
  - workspaces
  - cron
  - approval
```

### 三层职责

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| React 前端 | 对话渲染、团队标签、执行过程、产物预览、流式 reducer | 直接调用 LLM、直接写本地磁盘 |
| AgentDesk BFF | 任务状态、SSE 翻译、团队编排、技能挂载、产物索引、持久化 | 替代 QwenPaw agent loop |
| QwenPaw Runtime | 模型调用、工具执行、session、workspace、cron、审批 | AgentDesk 的任务列表和团队 UI 语义 |

## 数据存储

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| 任务元数据 | `{数据目录}/agentdesk/store.json` | 标题、runStatus、agent_id、轻量 transcript |
| 冷任务归档 | `{数据目录}/agentdesk/task_archives/{task_id}.json` | 大任务归档与 hydrate |
| 热路径 transcript | `task_store.py` 进程内 | 流式消息缓冲和有序写回 |
| AgentDesk session | `{数据目录}/agentdesk/sessions/` | task_id 到 QwenPaw session 的桥接 |
| 产物文件 | `{数据目录}/workspaces/{agent_id}/` | 由 QwenPaw 工具写入 workspace |

## 关键代码路径

| 路径 | 说明 |
| --- | --- |
| `src/qwenpaw/agentdesk/chat.py` | 单 agent 对话流适配 |
| `src/qwenpaw/agentdesk/chat_event_stream.py` | SSE 事件封装和副作用隔离 |
| `src/qwenpaw/agentdesk/team_chat.py` | 团队对话主编排 |
| `src/qwenpaw/agentdesk/team_event_bridge.py` | worker 事件到 UI 事件的桥接 |
| `src/qwenpaw/agentdesk/team_worker_bus.py` | 成员 worker stream 汇聚 |
| `src/qwenpaw/agentdesk/team_leader_runs.py` | Leader run 生命周期和 stale finalization |
| `src/qwenpaw/agentdesk/task_store.py` | 流式热路径任务状态 |
| `src/qwenpaw/agentdesk/store.py` | 持久化、归档和 payload slimming |
| `src/qwenpaw/agentdesk/session_bridge.py` | AgentDesk task 与 QwenPaw session 桥接 |
| `src/qwenpaw/agentdesk/skill_mount.py` | 技能挂载和 agent reload |
| `src/qwenpaw/agentdesk/web/src/utils/chatStreamReducer.ts` | 前端统一流式状态机 |
| `src/qwenpaw/agentdesk/web/src/pages/TaskChat/` | 任务对话页面 |

## 测试

后端重点回归：

```bash
pytest tests/unit/agentdesk/test_agentdesk_stream_side_effects.py tests/agentdesk/test_chat_run_status.py -q
pytest tests/unit/agentdesk/test_agentdesk_trace_events.py tests/unit/agentdesk/test_agentdesk_task_routes.py -q
pytest tests/agentdesk/test_team_chat.py -q
```

完整测试：

```bash
pytest
```

前端测试和构建：

```bash
cd src/qwenpaw/agentdesk/web
npm ci
npm run build
```

## 与 QwenPaw 的关系

AgentDesk2 基于 QwenPaw，但重点不是简单换皮。

QwenPaw 提供：

- agent runtime；
- 工具调用；
- session；
- workspace；
- cron；
- skill 基础能力；
- approval / security 等底层能力。

AgentDesk2 增加：

- 任务级产品模型；
- 数字员工和团队产品语义；
- Leader / Member 编排；
- 统一 SSE 协议；
- 前端流式 reducer；
- reconnect 和 stale run 处理；
- task transcript 持久化和归档；
- 产物文件索引和预览；
- 技能挂载到员工/对话的产品流程。

## 开源说明

这个仓库是完整可下载、可部署的项目快照，排除了 `.git`、`.env`、虚拟环境、构建缓存和本地测试缓存等不应进入公开仓库的内容。

如果你要基于它二次开发，建议先读：

1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md)
3. [docs/CASE_STUDY_STALE_TEAM_RUNS.md](docs/CASE_STUDY_STALE_TEAM_RUNS.md)

## License

Apache-2.0，见 [LICENSE](LICENSE)。



