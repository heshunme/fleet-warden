# FleetWarden 第一期设计文档

**文档版本**：v1.0
**产品名称**：FleetWarden
**阶段**：第一期 / MVP
**文档目标**：用于指导项目落地实现，统一产品、架构、研发与测试认知。

---

## 1. 文档目的

本文档用于回答以下问题：

1. FleetWarden 第一期究竟要做什么。
2. 系统应以什么样的架构来落地。
3. 各模块之间如何协作。
4. 核心数据模型和状态流转如何设计。
5. 前后端分别需要承担哪些职责。
6. 第一阶段应如何分步实现，以尽快得到可用版本。

本文档不是宣传材料，而是**研发落地设计文档**。其目标是让一个之前不了解项目的人，在阅读后能够开始实施系统设计、数据库设计、接口设计与前端实现。

---

## 2. 项目定义

### 2.1 一句话定义

FleetWarden 是一个基于 SSH 的多节点 AI 运维控制面。
用户通过 Web UI 选择节点并输入自然语言目标，系统先进行任务初始化，然后为每个节点分配独立 NodeAgent，在用户审批边界内逐轮推进任务执行。

### 2.2 第一阶段产品边界

FleetWarden 第一期只聚焦两种能力：

1. **模式 3：交互式 Agent 命令模式**
   本地 NodeAgent 为每个节点生成 shell command 提案，经审批后通过 SSH 执行。

2. **模式 4：交互式 Agent 委托模式**
   本地 NodeAgent 为每个节点生成“委托给远程 coding agent 的任务说明”，经审批后通过 SSH 调用远程 coding agent 非交互执行。

### 2.3 第一期明确不做

以下能力不在本期范围内：

* 模式 1：逐行命令执行
* 模式 2：整段脚本执行
* 完全无人值守自动运维
* 多人协作与复杂权限体系
* 被控端 FleetWarden 常驻 Agent
* 全局单一大 Agent 统一消化所有节点执行上下文

---

## 3. 设计原则

### 3.1 SSH 是唯一远程执行通道

FleetWarden 对目标节点的控制仅通过 SSH 完成。被控端不安装 FleetWarden 常驻服务。

### 3.2 初始化共享意图，执行阶段不共享推理

全体节点共享的是统一任务定义（TaskSpec），包括目标、约束、成功标准、风险边界等。
一旦任务启动，后续执行上下文按节点独立维护，不将所有节点执行结果混入同一个 Agent 上下文。

### 3.3 AI 负责提议，人类负责批准

第一期默认工作模式为**受监督执行**。
系统中的关键动作必须先由 Agent 提案，再由用户批准，之后才能执行。

### 3.4 每个节点独立推进

节点之间允许走不同路径。即使任务目标一致，不要求执行步骤一致。

### 3.5 每轮只提下一步，不做完整长计划

FleetWarden 不采用“预先生成完整计划再强行执行”的传统 workflow 设计。
每轮只生成**当前节点的下一步 proposal**，并依据上一轮结果动态推进。

### 3.6 执行成功不等于任务成功

命令退出码为 0 不代表任务完成。
系统必须区分：

* 动作执行成功
* 任务目标达成

### 3.7 全过程可追踪、可恢复、可审计

每轮 proposal、审批、执行、结果、状态变化都必须持久化。

---

## 4. 总体架构

### 4.1 架构概览

FleetWarden 第一期采用：

* **Web UI**：负责创建任务、审批 proposal、查看节点状态和结果
* **Python 后端**：负责业务编排、节点执行、Agent 交互、持久化

总体采用分层架构：

1. **Frontend（Web UI）**
2. **API Layer**
3. **Orchestrator Layer**
4. **Agent Layer**
5. **Executor Layer**
6. **Persistence Layer**
7. **Infrastructure Layer**

### 4.2 模块关系

#### Frontend

负责：

* 节点选择
* 任务创建
* TaskSpec 审批
* Proposal 审批
* 任务状态查看
* 节点详情查看

#### API Layer

负责：

* 接收前端请求
* 暴露任务、节点、proposal、approval 等接口
* 推送任务和节点状态变更事件

#### Orchestrator Layer

负责：

* 创建任务
* 驱动任务状态流转
* 为每个节点创建 NodeAgent 实例
* 管理每轮 proposal 与执行
* 管理停止、取消、暂停、重试等控制动作

#### Agent Layer

包含两类 Agent：

* **Initializer**：将用户自然语言整理为 TaskSpec
* **NodeAgent**：按节点维护 todo、历史、proposal 和成功判断

#### Executor Layer

负责实际远程动作执行。第一期至少包含两类执行器：

* **SSHCommandExecutor**
* **RemoteCodingAgentExecutor**

#### Persistence Layer

负责持久化以下内容：

* 节点数据
* 任务与 TaskSpec
* NodeAgent 状态
* 每轮 proposal
* 审批记录
* 执行结果
* 审计日志

#### Infrastructure Layer

负责：

* SSH 连接管理
* 后台任务执行
* 日志收集
* 配置管理
* LLM Provider 接入

---

## 5. 核心角色与责任

### 5.1 User

通过 Web UI 创建任务、审批提案、查看结果。

### 5.2 Initializer Agent

将用户输入的自然语言任务转化为统一任务定义 TaskSpec。

### 5.3 NodeAgent

每个节点一个 NodeAgent。
NodeAgent 只维护自己的本地上下文，不共享其他节点的执行细节。

### 5.4 Coordinator / Orchestrator

不是智能 Agent，而是编排器。负责：

* 驱动流程
* 管理状态
* 触发 Agent
* 调用执行器
* 聚合展示结果

### 5.5 Executor

负责在目标节点上执行 proposal 对应动作。

---

## 6. 核心对象模型

本节给出第一期必须具备的核心领域对象。

### 6.1 Node

表示一个可被 FleetWarden 控制的目标节点。

建议字段：

* `id`
* `name`
* `host_alias`
* `hostname`
* `port`
* `username`
* `ssh_config_source`
* `tags`
* `last_seen_at`
* `is_enabled`

### 6.2 Task

表示一次用户发起的顶层任务。

建议字段：

* `id`
* `title`
* `mode`（agent_command / agent_delegation）
* `user_input`
* `status`
* `created_by`
* `created_at`
* `updated_at`
* `approved_task_spec_id`
* `max_rounds_per_node`
* `auto_pause_on_risk`

### 6.3 TaskSpec

表示经 Initializer 产出并由用户批准后的统一任务定义。

建议字段：

* `id`
* `task_id`
* `goal`
* `constraints`
* `success_criteria`
* `risk_notes`
* `allowed_action_types`
* `disallowed_action_types`
* `initial_todo_template`
* `operator_notes`
* `approved_by`
* `approved_at`
* `version`

### 6.4 TaskNode

表示某个 Task 关联到某个 Node 的执行实例。

建议字段：

* `id`
* `task_id`
* `node_id`
* `status`
* `current_round`
* `stop_reason`
* `success_summary`
* `failure_summary`
* `needs_user_input`
* `last_result_at`

### 6.5 NodeAgentState

表示某节点 Agent 的内部状态。

建议字段：

* `id`
* `task_node_id`
* `task_spec_snapshot`
* `node_profile`
* `round_index`
* `todo_items`
* `observations`
* `attempted_actions`
* `last_proposal_id`
* `last_result_id`
* `success_assessment`
* `status`
* `snapshot_blob`
* `updated_at`

### 6.6 Round

表示某节点的一轮推进。

建议字段：

* `id`
* `task_node_id`
* `index`
* `status`
* `started_at`
* `ended_at`

### 6.7 Proposal

表示某轮中 NodeAgent 的动作提议。

建议字段：

* `id`
* `round_id`
* `proposal_type`（shell_command / remote_agent_task）
* `summary`
* `todo_delta`
* `rationale`
* `risk_level`
* `content`
* `editable_content`
* `created_at`

### 6.8 Approval

表示用户对 Proposal 的审批动作。

建议字段：

* `id`
* `proposal_id`
* `decision`（approved / edited_and_approved / rejected / paused）
* `edited_content`
* `comment`
* `approved_by`
* `approved_at`

### 6.9 ExecutionResult

表示 proposal 被执行后的结果。

建议字段：

* `id`
* `proposal_id`
* `executor_type`
* `exit_code`
* `stdout`
* `stderr`
* `structured_output`
* `execution_summary`
* `started_at`
* `ended_at`
* `is_action_successful`

### 6.10 AuditLog

表示关键事件日志。

建议字段：

* `id`
* `entity_type`
* `entity_id`
* `event_type`
* `payload`
* `operator_id`
* `created_at`

---

## 7. 状态机设计

### 7.1 顶层 Task 状态机

建议状态：

* `draft`
* `initializing`
* `awaiting_taskspec_approval`
* `running`
* `paused`
* `partially_succeeded`
* `succeeded`
* `failed`
* `cancelled`

状态说明：

* `draft`：任务创建中，尚未启动初始化
* `initializing`：正在生成 TaskSpec
* `awaiting_taskspec_approval`：等待用户批准 TaskSpec
* `running`：至少有一个 TaskNode 正在运行或等待 proposal 审批
* `paused`：任务被用户暂停
* `partially_succeeded`：部分节点成功，部分失败或终止
* `succeeded`：全部节点成功完成
* `failed`：全部节点失败或被阻断
* `cancelled`：用户取消任务

### 7.2 TaskNode 状态机

建议状态：

* `pending`
* `awaiting_proposal`
* `awaiting_approval`
* `executing`
* `evaluating`
* `succeeded`
* `failed`
* `paused`
* `blocked`
* `cancelled`

流转示意：

1. `pending`
2. `awaiting_proposal`
3. `awaiting_approval`
4. `executing`
5. `evaluating`
6. 根据结果进入：

   * `succeeded`
   * `awaiting_proposal`
   * `blocked`
   * `failed`
   * `paused`
   * `cancelled`

### 7.3 Round 状态机

建议状态：

* `draft`
* `proposal_ready`
* `approved`
* `executing`
* `completed`
* `rejected`
* `aborted`

---

## 8. 任务流程设计

### 8.1 任务创建流程

1. 用户打开任务创建页
2. 系统加载 SSH 节点列表
3. 用户选择节点
4. 用户选择模式（模式 3 或模式 4）
5. 用户输入自然语言任务
6. 用户点击“初始化任务”
7. 后端创建 Task 并进入 `initializing`
8. 调用 Initializer Agent
9. 生成 TaskSpec 草案
10. 任务进入 `awaiting_taskspec_approval`

### 8.2 TaskSpec 审批流程

1. 前端展示 TaskSpec
2. 用户可批准、修改后批准、拒绝
3. 批准后：

   * TaskSpec 固化为 approved version
   * 为每个选中的节点创建 TaskNode 和 NodeAgentState
   * Task 进入 `running`
4. 每个 TaskNode 进入 `awaiting_proposal`

### 8.3 单节点轮次流程

每个 TaskNode 的标准一轮：

1. Orchestrator 发现该 TaskNode 状态为 `awaiting_proposal`
2. 调用 NodeAgent 生成下一轮 Proposal
3. 保存 Proposal
4. TaskNode 进入 `awaiting_approval`
5. 前端显示 Proposal
6. 用户批准或编辑后批准
7. Orchestrator 将最终批准内容交给 Executor
8. Executor 通过 SSH 执行
9. 保存 ExecutionResult
10. TaskNode 进入 `evaluating`
11. NodeAgent 结合历史和结果评估：

* 是否达成 success_criteria
* 是否需要下一轮
* 是否需阻断/人工输入

12. 更新 TaskNode 状态

### 8.4 任务收敛流程

Task 的最终状态由所有 TaskNode 状态聚合得出：

* 全部 `succeeded` -> `succeeded`
* 部分 `succeeded`，其余 `failed/blocked/cancelled` -> `partially_succeeded`
* 全部 `failed/blocked/cancelled` -> `failed`
* 用户主动取消 -> `cancelled`

---

## 9. 模式 3 设计：交互式 Agent 命令模式

### 9.1 定义

NodeAgent 在每轮中输出：

* 本轮 todo 更新
* shell command proposal
* proposal rationale
* 风险等级
* 成功判定建议

### 9.2 Proposal 内容结构

建议结构化为：

* `summary`
* `why_this_step`
* `commands`
* `expected_signals`
* `risk_notes`
* `success_check`

### 9.3 执行方式

命令通过 SSH 执行。
第一期优先支持“单次远程 shell 执行”语义，不要求复杂交互会话。

### 9.4 注意事项

* 命令必须尽量可非交互运行
* 要考虑超时
* 要捕获 stdout/stderr
* 要保留原始输出供排查

---

## 10. 模式 4 设计：交互式 Agent 委托模式

### 10.1 定义

NodeAgent 在每轮中不直接产生命令，而是输出对目标节点远程 coding agent 的委托任务说明。

### 10.2 Proposal 内容结构

建议结构化为：

* `summary`
* `delegation_goal`
* `constraints`
* `allowed_scope`
* `disallowed_scope`
* `expected_output`
* `success_check`
* `risk_notes`

### 10.3 执行方式

RemoteCodingAgentExecutor 通过 SSH 在节点上调用指定 coding agent 的非交互模式，例如：

* codex
* claude code
* 未来可扩展适配器

### 10.4 设计要求

* Executor 层必须是可插拔的
* 远程 coding agent 的调用命令、参数、输出解析方式通过适配器实现
* NodeAgent 不应关心具体哪一种 coding agent，只依赖统一执行结果

---

## 11. NodeAgent 设计

### 11.1 NodeAgent 职责

NodeAgent 不是一个全局智能体，而是一个**单节点任务推进器**。
其职责是：

1. 读取该节点任务定义与历史上下文
2. 维护当前 todo
3. 生成下一轮 proposal
4. 在执行后评估是否成功
5. 判断是否继续、暂停、失败或请求人工输入

### 11.2 NodeAgent 输入

每次生成 proposal 时，至少应获得：

* TaskSpec
* Node 基本信息
* Node profile（若有）
* 历史 proposal
* 历史 execution results
* 当前 todo
* 当前轮次
* 最大轮次限制

### 11.3 NodeAgent 输出

至少包含：

* 更新后的 todo
* 当前 proposal
* rationale
* risk level
* success hypothesis
* 是否需要用户补充信息

### 11.4 NodeAgent 上下文原则

* 仅维护单节点上下文
* 不直接读取其他节点完整执行历史
* 后续可以引入“经验模式库”，但第一期不做强依赖

---

## 12. Initializer 设计

### 12.1 职责

Initializer 仅在任务开头运行一次。
负责将用户的自然语言目标整理为统一的 TaskSpec。

### 12.2 输出要求

Initializer 输出不应是长步骤列表，而应是“任务定义”：

* goal
* constraints
* success criteria
* risk notes
* initial todo template
* action boundaries

### 12.3 审批边界

Initializer 输出必须经过用户审批后才能进入执行阶段。

---

## 13. Executor 设计

### 13.1 SSHCommandExecutor

职责：

* 接收批准后的 shell command proposal
* 建立 SSH 连接
* 执行命令
* 收集 stdout/stderr/exit code
* 返回统一 ExecutionResult

关键要求：

* 支持超时
* 支持日志收集
* 支持基本异常归类（连接失败、认证失败、命令超时等）

### 13.2 RemoteCodingAgentExecutor

职责：

* 接收批准后的 delegation proposal
* 拼装远程 coding agent 的非交互调用命令
* 通过 SSH 在远端执行
* 解析返回内容
* 输出统一 ExecutionResult

关键要求：

* 每种远程 agent 都通过适配器实现
* 对标准输出做解析和摘要
* 支持失败场景的原始信息保留

### 13.3 Executor 统一返回结构

无论哪种执行器，统一返回至少应包含：

* `executor_type`
* `started_at`
* `ended_at`
* `exit_code`
* `stdout`
* `stderr`
* `structured_output`
* `execution_summary`
* `is_action_successful`

---

## 14. SSH 节点管理设计

### 14.1 节点来源

第一期从运行 FleetWarden 服务的环境中读取 SSH 配置。

### 14.2 基本要求

* 支持从 `.ssh/config` 解析 Host 条目
* 支持展示 Host、HostName、User、Port
* 支持搜索和多选
* 支持手动刷新

### 14.3 注意事项

第一期实现时应考虑基础兼容：

* `Include`
* `Host *`
* 别名
* 默认 User / Port

如部分高级 SSH 配置暂不完整支持，应在 UI 上明示。

---

## 15. Web UI 设计

### 15.1 页面结构

第一期建议至少包含以下页面：

1. 任务创建页
2. TaskSpec 审批页
3. 任务总览页
4. 节点详情页
5. 审批队列 / 待处理事项区域

### 15.2 任务创建页

应包含：

* 节点列表
* 搜索框
* 模式选择
* 自然语言输入框
* 初始化按钮

### 15.3 TaskSpec 审批页

应包含：

* goal
* constraints
* success criteria
* risk notes
* initial todo template
* 批准 / 编辑后批准 / 拒绝

### 15.4 任务总览页

应展示：

* Task 基本信息
* 模式
* 节点总数
* 成功/失败/运行中/等待审批节点数量
* 节点状态表格
* 最新事件流

### 15.5 节点详情页

应展示：

* 节点信息
* 当前状态
* 当前轮次
* 当前 todo
* 本轮 proposal
* 历史 proposal
* 审批记录
* 执行结果
* 原始 stdout/stderr

### 15.6 审批交互设计

用户必须能够：

* 批准单个节点 proposal
* 编辑 proposal 后批准
* 拒绝 proposal
* 暂停节点
* 取消整个任务

---

## 16. API 设计建议

本节不定义最终接口格式，但定义 API 分组。

### 16.1 Node API

* 获取节点列表
* 刷新 SSH 节点来源
* 获取节点详情

### 16.2 Task API

* 创建任务
* 获取任务列表
* 获取任务详情
* 取消任务
* 暂停任务
* 恢复任务

### 16.3 TaskSpec API

* 获取初始化结果
* 批准 TaskSpec
* 编辑后批准 TaskSpec
* 拒绝 TaskSpec

### 16.4 Proposal API

* 获取待审批 proposal 列表
* 获取 proposal 详情
* 批准 proposal
* 编辑后批准 proposal
* 拒绝 proposal
* 暂停对应 TaskNode

### 16.5 TaskNode API

* 获取任务下所有节点状态
* 获取单节点详情
* 获取单节点历史轮次

### 16.6 Event / Stream API

* 订阅任务事件
* 订阅节点状态变化
* 订阅新的待审批 proposal

---

## 17. 持久化设计建议

### 17.1 数据库

第一期建议使用关系型数据库，优先 SQLite 或 PostgreSQL。
若第一期以单机部署为主，可先从 SQLite 起步，但模型设计不要依赖 SQLite 特性。

### 17.2 持久化原则

以下数据必须入库：

* Task
* TaskSpec
* TaskNode
* NodeAgentState
* Round
* Proposal
* Approval
* ExecutionResult
* AuditLog

### 17.3 Snapshot 与恢复

NodeAgentState 应支持存储 snapshot。
系统重启后应尽可能恢复任务，不要求第一期做到任意时刻完全无损恢复，但至少要支持：

* 查到任务中断前状态
* 查到最新 proposal 和 result
* 对中断任务做继续或终止处理

---

## 18. 后台执行模型

### 18.1 原则

前端不直接绑定长执行流程。
任务推进必须在后端后台运行。

### 18.2 建议模型

第一期可以采用：

* API 进程
* 后台 Worker / Scheduler

由 Worker 负责：

* 拉取待处理 TaskNode
* 调用 NodeAgent
* 创建 Proposal
* 执行 Executor
* 写回结果

### 18.3 原因

这样设计有几个好处：

* 前后端解耦
* 任务执行不受浏览器页面影响
* 后续容易扩展到多 worker
* 方便演进为服务化部署

---

## 19. 审计与安全设计

### 19.1 审计要求

以下行为必须记录审计日志：

* 创建任务
* 批准 / 编辑 / 拒绝 TaskSpec
* 批准 / 编辑 / 拒绝 Proposal
* 执行动作
* 节点状态变更
* 任务状态变更

### 19.2 安全边界

第一期必须坚持：

* 不在被控端安装 FleetWarden Agent
* 不绕过用户审批直接执行高风险动作
* 原始输出可见，但要考虑在 UI 上避免无意暴露敏感信息

### 19.3 风险等级

Proposal 建议带 `risk_level` 字段，例如：

* low
* medium
* high

第一期虽不做自动批准策略，但可为后续无人值守模式打基础。

---

## 20. 可观察性设计

### 20.1 需要记录的日志类型

* API 请求日志
* Task 状态流转日志
* TaskNode 状态流转日志
* Executor 执行日志
* LLM 调用日志（不一定保存完整内容，但应保存 trace）

### 20.2 前端可见信息

前端应优先展示：

* 高层摘要
* 当前轮 proposal
* 执行结果摘要
* 原始输出展开区

避免一开始就让用户淹没在大量原始日志中。

---

## 21. 推荐技术栈

本节是建议，不是强制约束。

### 21.1 后端

建议：

* Python 3.11+
* FastAPI（API 层）
* SQLAlchemy / SQLModel（数据层）
* Pydantic（模型定义）
* AsyncSSH（SSH 执行）
* SQLite 或 PostgreSQL（持久化）

### 21.2 前端

建议：

* React
* TypeScript
* 任一成熟组件库
* 使用 SSE 或 WebSocket 接收任务更新

### 21.3 背景原因

此技术选型适合：

* Web 化
* 服务化
* 后续增加 worker
* 后续引入无人值守模式

---

## 22. MVP 实施顺序

第一期建议分 4 个阶段推进。

### 阶段一：骨架搭建

目标：跑通最小链路

包括：

* 项目初始化
* 数据模型落库
* Node 列表读取
* Task 创建
* TaskSpec 生成和审批
* 最简任务总览页

交付标志：

* 用户可以创建任务并完成 TaskSpec 审批

### 阶段二：模式 3 跑通

包括：

* NodeAgent 基础实现
* Proposal 生成
* Proposal 审批
* SSHCommandExecutor
* 执行结果写回
* 节点状态推进
* 节点详情页

交付标志：

* 用户可以在模式 3 下完成多节点逐轮推进

### 阶段三：模式 4 跑通

包括：

* RemoteCodingAgentExecutor
* executor adapter 机制
* 委托型 proposal UI
* 结果解析与展示

交付标志：

* 用户可以在模式 4 下委托远程 coding agent 执行任务

### 阶段四：稳定化

包括：

* 审计日志
* 错误处理
* 恢复机制
* 状态刷新优化
* UI 整理
* 基本测试

交付标志：

* 系统达到内部可试用水平

---

## 23. 测试建议

### 23.1 单元测试

应覆盖：

* Task 状态机
* TaskNode 状态机
* Proposal 审批逻辑
* 执行结果聚合逻辑
* NodeAgent 输入输出转换

### 23.2 集成测试

应覆盖：

* 创建任务到 TaskSpec 审批全流程
* 模式 3 单节点 / 多节点流程
* 模式 4 单节点 / 多节点流程
* Proposal 编辑后批准
* 节点失败后的下一轮推进

### 23.3 手工测试重点

重点验证：

* 节点差异场景
* 长输出日志场景
* SSH 连接失败场景
* proposal 被多次修改场景
* 服务重启后的状态恢复

---

## 24. 风险与取舍

### 24.1 主要风险

1. Agent 输出不稳定
2. 多节点并发下状态同步复杂
3. 模式 4 对远程 coding agent 的适配成本高
4. 审批流设计不清会导致用户体验差
5. 状态持久化和恢复设计不足会导致系统脆弱

### 24.2 第一阶段取舍建议

为控制复杂度，第一期应主动取舍：

* 不做复杂权限系统
* 不做经验共享闭环
* 不做自动批准策略
* 不做复杂 SSH 会话交互
* 不做完整企业级告警系统

---

## 25. 成功标准

第一期达到成功的标志是：

1. 用户可以通过 Web UI 选择节点并创建任务
2. 用户可以完成 TaskSpec 审批
3. 系统可以为每个节点独立推进 proposal / approval / execution / evaluation 循环
4. 模式 3 和模式 4 都可跑通
5. 节点之间上下文隔离明确
6. 任务、节点、proposal、执行结果都可被查看和追踪
7. 系统具备基本可恢复性与可审计性

---

## 26. 最终结论

FleetWarden 第一期的本质不是“再造一个 SSH 群发器”，也不是“做一个失控的全自动 Agent”。

它的本质是：

**一个以 SSH 为执行通道、以统一任务定义为起点、以每节点独立 Agent 为执行单元、以用户审批为边界的多节点 AI 运维控制面。**

第一期的实现重点，不是堆功能，而是把以下四件事做稳：

1. **TaskSpec 初始化**
2. **NodeAgent 独立推进**
3. **Proposal / Approval / Execution / Evaluation 循环**
4. **Web UI 的状态可视化与审计可追踪**

只要这四个支点稳定，FleetWarden 后续无论增加模式 1、2，还是演进到无人值守 AI 运维，都会有足够坚实的基础。
