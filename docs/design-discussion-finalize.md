# 设计方案：多轮交流 → LLM 纪要 → 正式总结

| 项目 | 内容 |
|------|------|
| 文档版本 | **v1.3** |
| 状态 | **后端 + CLI 已实现**；Streamlit 讨论室 / SSE 未做 |
| 关联 | [PRD.md](./PRD.md)、[api_contract.md](./api_contract.md) |

---

## 1. 产品定位

系统从「创建任务后后台一次性跑完流水线」改为 **两阶段决策辅助**：

1. **交流期（`discussing`）**  
   用户与 2～5 个 Agent 多轮对话；短回复、可追问。  
   **辩论模式**：用户为决策方；每轮可选「发言 / 辩手继续交锋 / 收束」；交锋顺序为支持方 → 反对方 → 评审。

2. **收束期（`finalizing` → `completed`）**  
   用户触发「生成正式分析」后：  
   - 单次 LLM 将讨论压缩为 **约 800 字纪要**；  
   - 各 Agent 基于纪要输出 **正式报告**（八段结构 + 六维 JSON）；  
   - 相似度、冲突、加权排名、综合建议（与现网一致）。

**原则**：不引入 LangChain；Python 服务层 + `asyncio` + `llm_chat`（system + user 拼历史）。

---

## 2. 核心流程

### 2.1 普通用户

```text
登录 → 创建任务（问题、模式、Agent 人设、可选 context_notes）
  → [CLI] 推荐人设 / 手动模板或自定义 / 辩论须指定立场
  → 进入讨论室（discussing）
  → 多轮：用户发言 → 全体专家各一条（非辩论）或 辩论整轮交锋
  → [辩论] 可选「辩手继续交锋」无需用户发言
  → 「生成正式分析」
  → finalizing：LLM 纪要 → 各 Agent 正式报告 → 后处理
  → completed：结果、图表、反馈、导出
```

### 2.2 状态机

```text
discussing → finalizing → completed
              ↓
           failed

# 兼容：LEGACY_AUTO_FINALIZE=1 时
pending → processing → completed | failed
```

| 状态 | 说明 |
|------|------|
| `discussing` | 交流进行中 |
| `finalizing` | 纪要 + 正式报告生成中 |
| `completed` | 可查看结果、反馈、导出 |
| `failed` | 收束失败，讨论记录保留 |
| `pending` / `processing` | 仅旧版一键分析 |

---

## 3. 决策模式差异（同一引擎）

| `decision_mode` | 交流期 | 收束期 | 默认人数 | 默认推荐编队 |
|-----------------|--------|--------|----------|--------------|
| `multi_angle` | 多角度；**带讨论历史** | 各 Agent 独立正式报告 | 3 | 木 + 金 + 土 |
| `expert_consult` | 专业诊断式短回复 + 历史 | 同上 | 3 | 木 + 火 + 水 |
| `risk_review` | 风险聚焦 + 历史 | 风险清单偏重 | 3 | 金 + 土 + 火 |
| `debate` | 支持→反对→评审；`agent-exchange` | 立场化正式报告 | **3（推荐）** | 木 + 金 + 水（仅建议立场） |

五行模板是 **人设库**；用户可 2～5 人、换人、全自定义。

---

## 4. Agent 人设（全模式统一）

### 4.1 配置来源

| 方式 | 行为 |
|------|------|
| **系统模板** | `template_id` + 可选字段覆盖，快照写入 `task_agents` |
| **完全自定义** | 手填四字段；`template_id` 为空 |
| **混合** | 同任务内可部分模板、部分自定义 |
| **可选叠加** | `extra_notes`（≤300 字），写入 Prompt |

**CLI 入口**（`python cli.py`）：

- **系统推荐**：`POST /api/templates/recommend`，按问题关键词匹配；辩论返回 `suggested_stance`（须用户确认立场）  
- **手动配置**：模板 / 自定义；字段带说明与示例（`cli_persona_help.py`）  
- **辩论人数**：先展示 2～5 人说明，默认 3；校验至少 1 正 + 1 反，评审 ≤1  

### 4.2 辩论专属

| 项 | 规则 |
|----|------|
| 默认人数 | 3（2=无评审；4～5=单方可加辩手） |
| `stance` | 创建时**用户指定** `pro` / `con` / `judge`（不靠模板名自动绑定） |
| 校验 | 至少 1×`pro` + 1×`con`；`judge` 最多 1 |
| 每轮后 | ① 用户发言（`debate_round`）② `POST .../debate/agent-exchange` ③ `finalize` |

### 4.3 人设 Prompt 片段

```text
你是「{agent_name}」{stance_label}。
【专业背景】{role_description}
【关注重点】{focus_area}
【表达风格】{tone}
【用户为本案补充】{extra_notes 或 无}
【本案背景说明】{context_notes}   ← 交流期 system 已接入
```

### 4.4 模板库扩展字段

`default_stance`、`recommended_modes`、`sort_order`、`display_alias`（种子见 `db/init_data.py`）。

---

## 5. 讨论交流期

### 5.1 消息模型 `discussion_messages`

| 字段 | 说明 |
|------|------|
| `seq` | 全局递增 |
| `role` | `user` / `agent` / `system` |
| `task_agent_id` | agent 消息必填 |
| `reply_scope` | 如 `all_brief`、`debate_round`、`agent_exchange` |

### 5.2 用户发消息 `POST /api/tasks/{id}/messages`

```json
{
  "content": "预算只有5万，且必须开学前上线。",
  "reply_scope": "all_brief"
}
```

| 模式 | `reply_scope` | 行为 |
|------|---------------|------|
| 非辩论 | `all_brief`（其他值会被归一化） | 全体专家各一条；**共享本轮前的讨论记录** |
| 辩论 | `debate_round`（`all_brief` 自动转换） | 支持 → 反对 → 评审 |

**历史上下文**（已实现）：

- 从 DB 加载 **seq &lt; 本轮用户消息** 的记录，格式化为 `【此前讨论记录】` 写入 user 提示  
- 条数上限 `DISCUSS_HISTORY_MAX_MESSAGES`（默认 12）  
- 总 prompt 上限 `DISCUSS_INPUT_MAX_CHARS`（默认 12000）  
- `context_notes` 写入 system（`persona.build_discuss_system_prompt`）  
- 辩论仍用 `debate_exchange.py` 中分角色 user 片段 + 同套 transcript 截断  

**交流期 LLM**：`DISCUSS_MAX_NEW_TOKENS=512`；禁止八段报告与 JSON 评分。

### 5.3 辩手自主交锋

`POST /api/tasks/{id}/debate/agent-exchange`：用户不发言，辩手再跑一轮；`debate_exchange_rounds` 计数。

### 5.4 限制

| 配置项 | 默认 |
|--------|------|
| `MAX_DISCUSSION_USER_TURNS` | 30 |
| `MAX_USER_MESSAGE_CHARS` | 500 |
| `MAX_DEBATE_EXCHANGE_ROUNDS` | 15 |

---

## 6. 收束期

`POST /api/tasks/{id}/finalize` → `FinalizePipeline`：LLM 纪要 → 并行正式报告 → 相似度 / 冲突 / 排名 → 综合建议。

纪要输入含 `context_notes` 与讨论 transcript（`discussion_summary.py`）。

---

## 7. 数据模型（摘要）

- `decision_tasks`：`context_notes`、`discussion_turns`、`discussion_summary`、`finalized_at`、`debate_exchange_rounds`  
- `task_agents`：`stance`、`template_id`、`extra_notes`、`sort_order`  
- `discussion_messages`：见 §5.1  
- 启动时 `db/migrate.py` 对 SQLite 做 `ALTER TABLE` 兼容旧库  

---

## 8. API 清单

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks/create` | 默认 `discussing` |
| POST | `/api/tasks/{id}/messages` | 用户发言 + Agent 回复 |
| GET | `/api/tasks/{id}/messages` | 时间线 |
| GET | `/api/tasks/{id}/debate-roster` | 辩手/专家席位 |
| POST | `/api/tasks/{id}/debate/agent-exchange` | 辩手自主交锋 |
| POST | `/api/tasks/{id}/finalize` | 收束 |
| GET | `/api/tasks/{id}/status` | 含 `discussion_turns`、`debate_exchange_rounds` |
| GET | `/api/tasks/{id}/result` | 讨论中可含 messages |
| POST | `/api/templates/recommend` | 推荐 Agent 组合 |

详见 [api_contract.md](./api_contract.md)。

---

## 9. 后端模块结构（当前实现）

```text
backend/
├── ai/
│   ├── prompts/
│   │   ├── persona.py              # 交流/收束人设 + 非辩论 user 历史拼接
│   │   └── debate_exchange.py      # 辩论交锋 Prompt、席位展示名
│   ├── discussion_summary.py
│   ├── orchestrators/finalize_pipeline.py
│   └── llm/chat.py
├── services/
│   ├── discussion_service.py
│   ├── finalize_service.py
│   ├── agent_config_resolver.py
│   ├── agent_recommender.py
│   └── task_runner.py              # submit_finalize
├── schemas/discussion.py
├── db/migrate.py
├── cli.py                          # 讨论室 + 创建流程
└── cli_persona_help.py             # 字段说明文案
```

---

## 10. 前端（Streamlit）— 未实现

| 页面 | 要点 |
|------|------|
| 创建 | 推荐 / 模板 / 自定义 / 辩论立场 |
| 讨论室 | 全体回复；辩论三选一菜单 |
| 收束 / 结果 | 轮询或 SSE |

**当前可用**：`python cli.py` 完整走通创建 → 讨论 → 收束 → 结果。

---

## 11. 配置项（os.env）

```env
# 讨论
MAX_DISCUSSION_USER_TURNS=30
DISCUSS_MAX_NEW_TOKENS=512
DISCUSS_HISTORY_MAX_MESSAGES=12
DISCUSS_INPUT_MAX_CHARS=12000
DISCUSSION_SUMMARY_TARGET_CHARS=800
DISCUSSION_SUMMARY_MAX_NEW_TOKENS=1024
SUMMARY_LLM_TEMPERATURE=0.3
MAX_DEBATE_EXCHANGE_ROUNDS=15

# 兼容旧 CLI 一键跑通
LEGACY_AUTO_FINALIZE=0
```

---

## 12. 实施计划与进度

| 阶段 | 交付 | 状态 |
|------|------|------|
| **P1** | DB + discussing + messages + DiscussionService | ✅ |
| **P2** | finalize + 纪要 + FinalizePipeline + stance 种子 | ✅ |
| **P3** | TaskCreate 校验 + recommend + api_contract | ✅ |
| **P4** | Streamlit 讨论室 + 创建页 | ⬜ |
| **P5** | SSE + CLI 适配 | ✅ CLI；⬜ SSE |

---

## 13. 与旧系统兼容

| 项 | 处理 |
|----|------|
| 旧 `completed` 任务 | 只读，无 `discussion_messages` |
| `LEGACY_AUTO_FINALIZE=1` | 创建后跳过讨论室，跑旧流水线 |
| PRD §8.5.3 固定多轮 | 由本方案替代 |

---

## 14. 答辩演示脚本（8 分钟）

1. 辩论：推荐人设 → 指定正/反/评审 → 讨论（发言 / 辩手交锋）→ 生成正式分析  
2. 展示：讨论记录 + 纪要驱动报告 + 冲突/相似度  
3. 多角度：自定义一名专家，多轮交流（可见前轮记忆）后收束  
4. 强调：模板或自定义、`context_notes`、辩论用户全程可控  

---

## 15. 明确不做（本期）

- LangChain / LangGraph  
- 交流期按单人/单方 `reply_scope`（已收敛为全体 / 辩论整轮）  
- PDF/Word 报告  

---

## 16. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-06-03 | 最终稿：交流→LLM纪要→收束 |
| v1.1 | 2026-06-03 | 辩论：用户指定立场；每轮三选一 |
| v1.2 | 2026-06-03 | 取消单方 reply_scope；非辩论带讨论历史 |
| v1.3 | 2026-06-03 | **实现归档**：推荐人设、CLI 字段说明、文档与 api_contract 对齐；标注 Streamlit/SSE 待做 |

---

## 17. v1.3 代码交付摘要（供 PR / 验收）

### 17.1 新增能力

- 讨论室状态机：`discussing` → `finalizing` → `completed`  
- 辩论：`debate_round` 顺序交锋、`agent-exchange`、席位 API  
- 人设：模板 / 自定义 / 微调；`POST /templates/recommend`  
- 非辩论交流：前轮 transcript + `context_notes`  
- CLI：创建（推荐+说明+辩论人数）、讨论室、收束  

### 17.2 主要文件

| 类型 | 路径 |
|------|------|
| 讨论 | `services/discussion_service.py` |
| 收束 | `services/finalize_service.py`, `ai/orchestrators/finalize_pipeline.py` |
| 纪要 | `ai/discussion_summary.py` |
| Prompt | `ai/prompts/persona.py`, `ai/prompts/debate_exchange.py` |
| API | `api/endpoints/tasks.py`, `schemas/discussion.py` |
| 迁移 | `db/migrate.py`, `db/models.py` |
| CLI | `cli.py`, `cli_persona_help.py` |

### 17.3 运行

```bash
# 根目录
cp os.env.example os.env   # 配置 LOCAL_MODEL_PATH 等
cd backend && python main.py   # 启动时自动 migrate

# 另一终端
cd backend && python cli.py
```

### 17.4 已知限制

- 无 Streamlit；无 SSE 流式  
- `all_brief` 下同轮各专家基于「本轮用户消息前」的同一快照，不包含同轮已生成的其他专家回复  
- 超长讨论依赖 `DISCUSS_HISTORY_MAX_MESSAGES` / `DISCUSS_INPUT_MAX_CHARS` 截断  
