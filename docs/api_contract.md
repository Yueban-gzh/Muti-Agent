# 接口约定（初稿）

> 由 **后端 A** 维护；字段变更需 A / B / 前端三人确认。

## 约定原则

- **B** 实现 `services/*` 与数据库；**A** 提供 HTTP 路由与鉴权。
- 前端只调用 A 暴露的 API，不直连数据库。

## 接口清单（待补充）

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/auth/register` | 注册 | 待开发 |
| POST | `/auth/login` | 登录 | 待开发 |
| POST | `/auth/logout` | 退出 | 待开发 |
| GET | `/auth/me` | 当前用户 | 待开发 |
| POST | `/debate/start` | 创建分析任务 | 待开发 |
| GET | `/debate/status/{task_id}` | 任务状态 | 待开发 |
| GET | `/debate/result/{task_id}` | 任务结果 | 待开发 |
| POST | `/feedback/vote` | 用户采纳反馈 | 待开发 |
| GET | `/history/my` | 我的历史 | 待开发 |
| GET | `/history/{task_id}` | 任务详情 | 待开发 |

## B 提供给 A 的 Service（待 B 实现）

```python
# services/auth_store.py
def create_user(...) -> str: ...
def verify_password(username: str, password: str) -> str | None: ...
def get_user_role(user_id: str) -> str: ...

# services/debate_service.py
async def start(task_id: str, user_id: str, payload: dict) -> None: ...
async def get_status(task_id: str) -> str: ...
async def get_result(task_id: str) -> dict: ...
```

## 结果页字段（B 与前端对齐，第二阶段前冻结）

- `agents[]`: `name`, `persona`, `answer`, `scores`（六维）
- `similarity_matrix`, `conflicts[]`, `summary`, `weighted_ranking[]`
- `feedback`: 用户采纳状态
