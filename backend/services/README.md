# 业务服务层（backend/services）

后端 B 主责。API 层（`api/endpoints`）通过本目录调用业务逻辑，不直接拼装复杂 SQL 或 Markdown。

| 模块 | 职责 |
|------|------|
| `task_service.py` | 创建任务、状态/结果查询、权限校验 |
| `history_service.py` | 用户历史列表 |
| `report_service.py` | Markdown 报告生成 |
| `pipeline_service.py` | 触发 `ai/agent_core` 后台流水线 |
| `repositories/` | 按实体封装数据库查询 |
