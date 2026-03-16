# FleetWarden

FleetWarden 是一个 SSH-first 的 AI 运维控制面。用户通过 Web UI 选择节点、输入自然语言目标，系统先生成统一的任务定义 `TaskSpec`，再按节点逐轮生成 proposal，经人工审批后通过 SSH 执行，并把 proposal、审批、执行结果和状态变化持久化下来。

当前仓库是一个可运行的 V1/MVP，实现重点是“受监督的多节点执行编排”，不是完整自动化运维平台。

## V1 范围

基于 `docs/PRD_v1.md`，当前版本聚焦两种模式：

- `agent_command`：NodeAgent 为节点生成 shell command proposal，审批后经 SSH 执行
- `agent_delegation`：NodeAgent 生成“委托给远程 coding agent”的任务说明，审批后通过 SSH 调用远程 agent

当前明确不做：

- 逐行命令模式
- 整段脚本模式
- 完全无人值守执行
- 被控端常驻 FleetWarden agent
- 多人协作和复杂权限体系

## 当前已落地能力

后端已实现：

- FastAPI API
- SQLite 持久化
- 基于 `~/.ssh/config` 的节点发现，支持 `Host`、`HostName`、`User`、`Port`、`Include`、`Host *` 默认值
- Task / TaskSpec / TaskNode / Round / Proposal / Approval / ExecutionResult / AuditLog 数据模型
- 任务创建、TaskSpec 审批、proposal 审批/拒绝/暂停节点
- 后台 worker 轮询 `awaiting_proposal` 节点并生成 proposal
- worker 启动时把残留 `executing` 节点恢复为 `blocked`
- SSE 事件流，用于任务和 proposal 状态刷新

前端已实现：

- 节点列表与刷新
- 任务创建
- TaskSpec 审批页
- 任务总览
- 节点详情
- 审批队列
- 基于 SSE 的任务事件更新

当前 agent 逻辑仍是确定性 stub，用于打通流程，不是正式 LLM 集成。

## 技术栈

### Backend

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- AsyncSSH
- SQLite
- `uv`

### Frontend

- React
- TypeScript
- Vite
- npm

## 项目结构

```text
.
├── backend/        # FastAPI API、orchestrator、executor、worker、持久化
├── frontend/       # React 控制台
├── docs/PRD_v1.md  # V1 产品/架构设计文档
└── start-dev.sh    # 一键启动 API、worker、frontend
```

关键文件：

- `backend/app/main.py`：API 入口，数据库初始化放在 FastAPI lifespan startup
- `backend/app/api/routes.py`：V1 API 路由
- `backend/app/orchestrator/service.py`：核心编排逻辑和状态流转
- `backend/app/worker.py`：后台轮询 worker
- `backend/app/infra/ssh_config.py`：SSH 配置解析和节点发现
- `frontend/src/App.tsx`：主控制台页面
- `frontend/src/lib/api.ts`：前端 API client

## 快速开始

### 依赖要求

- Python 3.11+
- `uv`
- Node.js + npm
- 本机可用的 SSH 配置文件，默认读取 `~/.ssh/config`

### 一键启动

在仓库根目录运行：

```bash
./start-dev.sh
```

默认会启动：

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- API Base: `http://localhost:8000/api`
- Worker: 后台轮询进程

## 分模块启动

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

另开一个终端启动 worker：

```bash
cd backend
uv run fleetwarden-worker
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

生产构建：

```bash
cd frontend
npm run build
```

## 运行配置

后端当前配置定义在 `backend/app/config.py`，默认值包括：

- 数据库：`sqlite:///./fleetwarden.db`（实际位于仓库根目录）
- SSH 配置路径：`~/.ssh/config`
- SSH 命令超时：`60s`
- worker 轮询间隔：`1s`
- 远程 agent 命令：`codex exec --json`

前端默认访问：

- `VITE_API_BASE_URL=http://localhost:8000/api`

如果需要修改前端 API 地址，可在启动前设置环境变量。

## 使用流程

### 1. 刷新节点

前端会调用 `POST /api/nodes/refresh`，从 SSH 配置导入节点。

每个节点会记录：

- `host_alias`
- `hostname`
- `username`
- `port`
- `ssh_config_source`
- `capability_warnings`

### 2. 创建任务

用户选择节点并提交：

- 标题
- 模式：`agent_command` 或 `agent_delegation`
- 自然语言目标
- `max_rounds_per_node`

创建后任务进入 `awaiting_taskspec_approval`。

### 3. 审批 TaskSpec

Initializer 会先把自然语言目标整理为 `TaskSpec`，包括：

- `goal`
- `constraints`
- `success_criteria`
- `risk_notes`
- `allowed_action_types`
- `disallowed_action_types`
- `initial_todo_template`
- `operator_notes`

用户可编辑后审批；审批完成后任务进入 `running`，各节点进入 `awaiting_proposal`。

### 4. worker 生成 proposal

后台 worker 会轮询等待中的节点，并为每个节点生成一条下一步 proposal。V1 设计上强调：

- 每个节点独立推进
- 每轮只提“下一步”，不是一次生成完整长计划
- proposal 必须先审批后执行

### 5. 审批 proposal

审批队列支持：

- `approve`
- `reject`
- `pause-node`

审批通过后，系统会选择对应 executor：

- `SSHCommandExecutor`
- `RemoteCodingAgentExecutor`

执行结果会写入 `ExecutionResult`，并更新节点状态、round 状态、agent state 和审计日志。

### 6. 查看结果与审计

前端可以查看：

- 任务总览
- 节点状态
- 每轮 proposal
- 审批记录
- 执行结果
- 事件流更新

## 核心状态机约束

这部分是当前实现里最容易出问题的区域，README 明确记录代码实际约束：

- 恢复被暂停任务时，如果节点已经存在待审批 proposal，节点必须回到 `awaiting_approval`，不能回到 `awaiting_proposal`
- 从审批队列执行 `pause-node` 时，proposal 不能继续保持 `pending`
- `list_pending_proposals()` 必须同时过滤：
  - `Proposal.status == "pending"`
  - `TaskNode.status == "awaiting_approval"`
- worker 启动时会把残留在 `executing` 的节点恢复为 `blocked`

这些行为在测试里已有覆盖，主要集中在：

- `backend/tests/test_orchestrator.py`
- `backend/tests/test_state_machine.py`

## API 摘要

当前 V1 主要 API：

- `GET /api/nodes`
- `POST /api/nodes/refresh`
- `GET /api/nodes/{node_id}`
- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/pause`
- `POST /api/tasks/{task_id}/resume`
- `POST /api/tasks/{task_id}/cancel`
- `GET /api/tasks/{task_id}/taskspec`
- `POST /api/tasks/{task_id}/taskspec/approve`
- `POST /api/tasks/{task_id}/taskspec/reject`
- `GET /api/proposals?status=pending`
- `GET /api/proposals/{proposal_id}`
- `POST /api/proposals/{proposal_id}/approve`
- `POST /api/proposals/{proposal_id}/reject`
- `POST /api/proposals/{proposal_id}/pause-node`
- `GET /api/tasks/{task_id}/nodes`
- `GET /api/task-nodes/{task_node_id}`
- `GET /api/task-nodes/{task_node_id}/rounds`
- `GET /api/tasks/{task_id}/events`
- `GET /api/proposals/events`
- `GET /healthz`

## 测试

后端测试：

```bash
cd backend
uv run python -m pytest
```

当前测试覆盖重点：

- API 基础流程
- orchestrator 生命周期
- 暂停/恢复语义
- proposal 审批和执行结果写入
- SSH config 解析
- 聚合状态机行为

注意：测试会切换到每次临时创建的 SQLite 文件，不应指向仓库根目录下的运行时数据库。

## 当前限制

- Agent 逻辑仍是 stub，不代表真实 LLM 推理能力
- 默认数据库是 SQLite，适合本地开发，不适合高并发生产场景
- 没有完整鉴权、RBAC、多租户能力
- 没有被控端常驻 agent
- 没有 WebSocket，事件刷新当前基于 SSE
- 前端仍是 V1 控制台形态，不是完整多页面产品

## 开发建议

修改后端编排逻辑时，建议顺序：

1. 读 `docs/PRD_v1.md`
2. 读 `backend/app/orchestrator/service.py`
3. 读对应测试
4. 修改代码
5. 增加回归测试
6. 运行 `uv run python -m pytest`

修改前端时，至少执行：

```bash
cd frontend
npm run build
```

并确认前端类型与后端 schema 保持一致：

- `backend/app/api/schemas.py`
- `frontend/src/types.ts`

## 文档与参考

- 产品设计文档：`docs/PRD_v1.md`
- 协作说明：`AGENTS.md`
