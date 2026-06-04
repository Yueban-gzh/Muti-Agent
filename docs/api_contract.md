# 接口约定

> 由**后端 A** 实现并维护；字段变更需 A / B / 前端三人确认。

---

## 接口清单

所有接口前缀统一为 `/api`，返回 JSON。除注册/登录外均需 `Authorization: Bearer <JWT>` 请求头。

### 认证模块 (`/api/auth`)

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/auth/register` | 无 | 注册新用户 |
| POST | `/api/auth/login` | 无 | 登录，返回 JWT |
| GET | `/api/auth/me` | Bearer | 获取当前用户信息 |

### 决策任务 (`/api/tasks`)

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/tasks/create` | 用户 | 创建任务，默认进入 `discussing` 讨论室 |
| POST | `/api/tasks/{task_id}/messages` | 用户 | 讨论期发送消息并触发 Agent 回复 |
| GET | `/api/tasks/{task_id}/messages` | 用户 | 讨论消息时间线 |
| GET | `/api/tasks/{task_id}/debate-roster` | 用户 | 辩论辩手席位（含 `stance` / `stance_label`） |
| POST | `/api/tasks/{task_id}/debate/agent-exchange` | 用户 | 用户不发言，辩手自主交锋一轮（支持→反对→评审） |
| POST | `/api/tasks/{task_id}/finalize` | 用户 | 结束讨论 → LLM 纪要 → 正式报告（`finalizing`→`completed`） |
| GET | `/api/tasks/{task_id}/status` | 用户 | 轮询状态（discussing/finalizing/completed/failed） |
| GET | `/api/tasks/{task_id}/result` | 用户 | 讨论中返回 messages；完成后含 outputs、相似度、冲突、综合建议 |
| POST | `/api/templates/recommend` | 用户 | 按问题关键词推荐 Agent 组合 |

### 用户反馈 (`/api/feedback`)

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/feedback/vote` | 用户 | 提交采纳反馈（agent / summary / none） |
| GET | `/api/feedback/stats` | 管理员 | 反馈采纳统计 |

### 历史记录 (`/api/history`)

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/history/` | 用户 | 当前用户的任务列表（倒序） |
| GET | `/api/history/{task_id}/export` | 用户 | 导出 Markdown 报告下载 |

### 模板查询 (`/api/templates`)

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/templates/` | 用户 | 获取启用的模板列表 |
| GET | `/api/templates/all` | 用户 | 获取全部模板（管理员可见未启用的） |

### 管理员后台 (`/api/admin`)

> 全部需要管理员角色，否则返回 403。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/users` | 所有用户列表 |
| GET | `/api/admin/tasks` | 全站任务列表（支持 limit/offset） |
| GET | `/api/admin/stats` | 全局数据看板 |
| POST | `/api/admin/templates` | 创建模板 |
| PUT | `/api/admin/templates/{template_id}` | 更新模板 |
| DELETE | `/api/admin/templates/{template_id}` | 删除模板 |
| GET | `/api/admin/logs` | 操作日志查询（支持 event_type 筛选） |

### 操作日志 event_type 枚举

| event_type | 说明 |
|------------|------|
| `user.register` | 用户注册 |
| `user.login` | 用户登录 |
| `task.create` | 创建决策任务 |
| `task.processing` | 任务开始 AI 分析 |
| `task.completed` | 任务分析完成 |
| `task.failed` | 任务失败或流水线异常 |
| `agent.all_failed` | 全部 Agent 调用失败 |
| `feedback.vote` | 用户提交采纳反馈 |
| `llm.load_failed` | 本地模型启动加载失败 |

---

## 请求/响应格式示例

### POST `/api/tasks/create`

```json
{
  "question": "是否应该开发校园二手交易小程序？",
  "decision_mode": "multi_angle",
  "agent_count": 2,
  "agents": [
    {
      "agent_name": "木·生长型",
      "role_description": "产品创新专家",
      "focus_area": "增长机会、长期价值",
      "tone": "鼓励型"
    },
    {
      "agent_name": "金·决断型",
      "role_description": "法务风控专家",
      "focus_area": "法律合规、失败风险",
      "tone": "严谨型"
    }
  ],
  "weight_config": "{\"benefit\":0.2,\"cost\":0.2,\"risk\":0.2,\"tech\":0.15,\"exec\":0.15,\"long_term\":0.1}"
}
```

### Response `200`

```json
{
  "task_id": 1,
  "status": "pending",
  "message": "任务已提交，正在后台处理"
}
```

### GET `/api/tasks/{task_id}/result`

```json
{
  "task_id": 1,
  "question": "...",
  "decision_mode": "multi_angle",
  "agent_count": 2,
  "weight_config": "...",
  "status": "completed",
  "error_message": null,
  "final_summary": "# 综合建议\n...",
  "created_at": "2026-05-30T10:00:00Z",
  "agents": [
    {
      "id": 1,
      "task_id": 1,
      "agent_name": "木·生长型",
      "role_description": "...",
      "focus_area": "...",
      "tone": "...",
      "final_prompt": "..."
    }
  ],
  "outputs": [
    {
      "id": 1,
      "task_id": 1,
      "task_agent_id": 1,
      "agent_name": "木·生长型",
      "output_text": "## 观点摘要\n...",
      "score_json": "{\"benefit\":8,\"cost\":7,\"risk\":6,\"tech\":9,\"exec\":8,\"long_term\":8}",
      "created_at": "..."
    }
  ],
  "similarities": [
    {
      "id": 1,
      "task_id": 1,
      "agent_id_1": 1,
      "agent_id_2": 2,
      "similarity": 0.7382,
      "explanation": "「木·生长型」与「金·决断型」的观点高度相似...",
      "created_at": "..."
    }
  ],
  "conflicts": [
    {
      "id": 1,
      "task_id": 1,
      "dimension": "risk",
      "max_score": 8.0,
      "min_score": 4.0,
      "conflict_level": "high",
      "explanation": "在「风险可控性」维度上存在明显分歧...",
      "created_at": "..."
    }
  ],
  "weighted_ranking": [
    {
      "task_agent_id": 1,
      "agent_name": "木·生长型",
      "scores": {
        "benefit": 8.0,
        "cost": 7.0,
        "risk": 6.0,
        "tech": 9.0,
        "exec": 8.0,
        "long_term": 8.0
      },
      "total_score": 7.55,
      "rank": 1,
      "score_available": true
    }
  ]
}
```

### POST `/api/feedback/vote`

```json
{
  "task_id": 1,
  "chosen_type": "agent",
  "chosen_agent_id": 1,
  "comment": "这个角度很有启发"
}
```

### GET `/api/admin/stats`

管理员全局看板。在原有用户/任务/反馈/模板统计基础上，追加运行时调度指标：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_queue_depth` | int | 任务队列中等待执行的任务数 |
| `pipeline_active` | int | 当前正在执行的流水线数 |
| `pipeline_max` | int | 流水线并发上限（`MAX_CONCURRENT_PIPELINES`） |
| `llm_active` | int | 当前占用 LLM 槽位的请求数 |
| `llm_max` | int | LLM 并发槽位上限（`LLM_MAX_CONCURRENT`） |
| `llm_available_slots` | int | LLM 剩余可用槽位数 |

```json
{
  "total_users": 10,
  "total_tasks": 25,
  "completed_tasks": 20,
  "failed_tasks": 1,
  "pending_tasks": 4,
  "task_queue_depth": 2,
  "pipeline_active": 1,
  "pipeline_max": 3,
  "llm_active": 1,
  "llm_max": 2,
  "llm_available_slots": 1
}
```

---

## 决策模式枚举

| 值 | 名称 | 说明 |
|----|------|------|
| `multi_angle` | 多角度分析 | 各 Agent 从自身角度独立分析 |
| `debate` | 正反辩论 | 创建时**必须为每位辩手指定** `stance`（`pro`/`con`/`judge`）；至少 1 正方 + 1 反方；模板 `default_stance` 仅作推荐提示 |

### 辩论模式交互要点

| 阶段 | 行为 |
|------|------|
| 创建任务 | 每个 `agents[]` 项必填 `stance`：`pro`（支持方）、`con`（反对方）、`judge`（评审，最多 1 人） |
| 推荐组合 | `POST /api/templates/recommend` 在 `debate` 下返回 `suggested_stance`，**不**自动写入 `stance` |
| 用户发言 | 非辩论：`reply_scope=all_brief`（全体各一条）；辩论：`debate_round`（或 `all_brief` 自动转换）。**不支持**指定单个 Agent/单方 |
| 用户不发言 | `POST .../debate/agent-exchange`：辩手基于已有记录再交锋一轮；`debate_exchange_rounds` 计数 |
| 结束 | `POST .../finalize` |

`GET /api/tasks/{id}/status` 在辩论任务中额外返回 `debate_exchange_rounds`（已完成的辩手自主交锋轮数）。
| `expert_consult` | 专家会诊 | 不同领域专家联合诊断 |
| `risk_review` | 风险评审 | 重点分析失败风险和应对 |

## 六维评分维度

| key | 中文名 | 范围 |
|-----|--------|------|
| benefit | 收益潜力 | 1~10 |
| cost | 成本可控性 | 1~10 |
| risk | 风险可控性 | 1~10 |
| tech | 技术可行性 | 1~10 |
| exec | 执行可行性 | 1~10 |
| long_term | 长期价值 | 1~10 |

## 加权综合得分

`GET /api/tasks/{task_id}/result` 返回 `weighted_ranking` 数组，按 `rank` 升序（未评分的 `rank` 为 `null`）。

```
综合得分 = Σ (维度分数 × 对应权重)
```

默认权重与 `weight_config` 一致：benefit 20%、cost 20%、risk 20%、tech 15%、exec 15%、long_term 10%。

## 任务状态流转

```
discussing → finalizing → completed
          → failed

# 兼容旧路径（LEGACY_AUTO_FINALIZE=1）
pending → processing → completed
                     → failed
```

## 采纳类型枚举

| 值 | 说明 |
|----|------|
| `agent` | 采纳某个 Agent（需提供 chosen_agent_id） |
| `summary` | 采纳系统综合建议 |
| `none` | 暂不采纳 |
