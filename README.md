# 可配置多智能体决策辅助系统

基于 Python 的课程实践项目：用户可配置 Agent 数量与人设、决策模式与维度权重，系统通过多智能体分析、评分矩阵、语义相似度与冲突检测生成综合建议，并支持反馈与历史记录。

> 本项目面向《Python 程序设计》AI 方向课程实践，重点考察 GUI、权限、网络、数据库、本地 AI 能力与工程化设计。

## 产品一句话

输入决策问题 → 配置 2–5 个 Agent → 多角度分析 → 相似度 / 冲突 / 评分可视化 → 综合建议 → 采纳反馈与历史报告。

## 技术栈（规划）

| 层级 | 技术 |
|------|------|
| 前端 | Streamlit（或 PyQt6，以课程要求为准） |
| 应用 API | FastAPI |
| 数据 | SQLite |
| AI | 本地轻量模型 + `sentence-transformers` 向量化；进阶可选 vLLM |

## 团队分工

| 角色 | 职责 |
|------|------|
| **后端 A** | 权限、任务调度、历史/反馈/管理员/报告导出等 **API**；维护接口文档；**不直接写 SQL、不碰模型** |
| **后端 B** | 数据库、`services` 层、Prompt、多 Agent 分析、评分/相似度/冲突/综合建议；**B 提供 service，A 包成 API** |
| **前端** | 登录、任务创建、Agent 配置、权重、结果页、历史、管理员后台、Plotly 可视化 |

### 协作规则

- A 不直接写数据库；前端不直连数据库、不调用模型  
- B 提供 `services/*`，A 负责 HTTP 路由与鉴权  
- 接口字段变更需 **三人确认**  

## 目录结构（规划）

```
muti-agent/
├── README.md
├── requirements.txt
├── config.example.yaml
├── api/                 # 后端 A：FastAPI 路由、鉴权、调度
├── services/            # 后端 B：业务与 AI 核心（供 A 调用）
├── db/                  # 后端 B：表结构、初始化、CRUD
├── llm/                 # 后端 B：模型与生成（可选）
├── prompts/             # 后端 B：Agent 模板与 Prompt
├── ui/                  # 前端：Streamlit / PyQt 页面
├── tests/
├── docs/                # 接口文档、实验报告等
└── logs/
```

## 环境要求

- Python 3.10+
- 建议使用虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 快速开始（待实现）

```bash
# 1. 初始化数据库
python -m db.init_db

# 2. 启动 API（后端 A）
uvicorn api.main:app --reload --port 8000

# 3. 启动前端
streamlit run ui/app.py
```

具体命令与配置在各模块就绪后补充至 `docs/运行说明.md`。

## 开发阶段

| 阶段 | 时间 | 目标 |
|------|------|------|
| 一 | 3–5 天 | 登录 → 创建任务 → **mock 结果** → 反馈 → 历史 |
| 二 | 5–7 天 | 真实多 Agent、评分、相似度、冲突、综合建议、图表 |
| 三 | 3–5 天 | 管理员后台、报告导出、联调、答辩演示 |

## 文档

| 文档 | 说明 |
|------|------|
| [docs/PRD.md](docs/PRD.md) | 完整产品需求文档 |
| [docs/团队分工.md](docs/团队分工.md) | 三人分工、排期与协作规则 |
| [docs/api_contract.md](docs/api_contract.md) | 接口约定（A 维护） |

## 许可证

课程实践项目，仅供教学使用。
