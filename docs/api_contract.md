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
| POST | `/api/tasks/create` | 用户 | 创建任务 + 触发后台 AI 分析流水线 |
| GET | `/api/tasks/{task_id}/status` | 用户 | 轮询任务状态（pending→processing→completed/failed） |
| GET | `/api/tasks/{task_id}/result` | 用户 | 获取完整结果（Agent 输出 + 相似度 + 冲突 + 综合建议） |

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

---

## 决策模式枚举

| 值 | 名称 | 说明 |
|----|------|------|
| `multi_angle` | 多角度分析 | 各 Agent 从自身角度独立分析 |
| `debate` | 正反辩论 | Agent 分为支持方和反对方 |
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

## 任务状态流转

```
pending → processing → completed
                     → failed
```

## 采纳类型枚举

| 值 | 说明 |
|----|------|
| `agent` | 采纳某个 Agent（需提供 chosen_agent_id） |
| `summary` | 采纳系统综合建议 |
| `none` | 暂不采纳 |
