"""
历史记录与报告导出接口
---------------------
提供用户历史决策任务列表查询和 Markdown 报告导出的 API。
所有接口挂载在 /api/history 路由前缀下，需要用户登录。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.dependencies import get_current_user
from db.database import get_db
from db.models import (
    User,
    DecisionTask,
    TaskAgent,
    AgentOutput,
    SimilarityResult,
    ConflictResult,
)

# ============================================================================
# 路由初始化
# ============================================================================

router = APIRouter(prefix="/api/history", tags=["历史记录"])


# ============================================================================
# GET /api/history/ — 当前用户历史任务列表
# ============================================================================


@router.get(
    "/",
    summary="获取历史任务列表",
    description="返回当前登录用户的所有历史决策任务，按创建时间倒序排列。",
)
async def get_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    查询当前用户的历史决策任务列表。

    返回:
        list[dict]: 任务摘要列表，包含 id, question, decision_mode, created_at, status
    """
    result = await db.execute(
        select(DecisionTask)
        .where(DecisionTask.user_id == current_user.id)
        .order_by(desc(DecisionTask.created_at))
    )
    tasks = result.scalars().all()

    return [
        {
            "id": task.id,
            "question": task.question,
            "decision_mode": task.decision_mode,
            "agent_count": task.agent_count,
            "status": task.status,
            "created_at": task.created_at.isoformat(),
        }
        for task in tasks
    ]


# ============================================================================
# GET /api/history/{task_id}/export — 导出 Markdown 报告
# ============================================================================


@router.get(
    "/{task_id}/export",
    summary="导出决策报告（Markdown）",
    description="将指定任务的完整分析结果排版为 Markdown 格式，以 .md 文件下载。",
    response_class=PlainTextResponse,
)
async def export_report(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """
    生成 Markdown 格式的决策分析报告并触发浏览器下载。

    报告包含：
        - 决策问题与基本信息
        - 各 Agent 的完整分析意见
        - 语义相似度分析
        - 观点冲突检测
        - 最终综合建议

    参数:
        task_id: 要导出的任务 ID
        current_user: 当前登录用户
        db: 异步数据库会话

    返回:
        PlainTextResponse: Markdown 格式文本，Content-Disposition 触发下载
    """
    # --- 查询任务及全部关联数据 ---
    result = await db.execute(
        select(DecisionTask)
        .where(DecisionTask.id == task_id)
        .options(
            selectinload(DecisionTask.task_agents),
            selectinload(DecisionTask.agent_outputs),
            selectinload(DecisionTask.similarity_results),
            selectinload(DecisionTask.conflict_results),
        )
    )
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")
    if task.status != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能导出已完成的任务")

    # --- 构建 agent_name 映射 ---
    agent_name_map = {a.id: a.agent_name for a in task.task_agents}
    agent_output_map = {o.task_agent_id: o for o in task.agent_outputs}

    # =========================================================================
    # 组装 Markdown 报告
    # =========================================================================
    lines = []

    # 标题
    lines.append(f"# 多智能体决策分析报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # 决策模式中文映射
    mode_map = {
        "multi_angle": "多角度分析",
        "debate": "正反辩论",
        "expert_consult": "专家会诊",
        "risk_review": "风险评审",
    }

    # 基本信息
    lines.append("## 一、决策问题")
    lines.append("")
    lines.append(f"> {task.question}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 二、分析配置")
    lines.append("")
    lines.append(f"- **决策模式**: {mode_map.get(task.decision_mode, task.decision_mode)}")
    lines.append(f"- **参与 Agent 数量**: {task.agent_count} 个")
    if task.weight_config:
        lines.append(f"- **用户权重**: `{task.weight_config}`")
    lines.append("")

    # Agent 人设
    lines.append("### 参与分析的 Agent")
    lines.append("")
    lines.append("| # | Agent 名称 | 专业背景 | 关注领域 | 输出风格 |")
    lines.append("|---|-----------|---------|---------|---------|")
    for i, agent in enumerate(task.task_agents, 1):
        role = agent.role_description or "-"
        focus = agent.focus_area or "-"
        tone = agent.tone or "-"
        lines.append(f"| {i} | {agent.agent_name} | {role} | {focus} | {tone} |")
    lines.append("")

    # 各 Agent 分析意见
    lines.append("---")
    lines.append("")
    lines.append("## 三、各专家分析意见")
    lines.append("")

    for agent in task.task_agents:
        lines.append(f"### {agent.agent_name}")
        lines.append("")
        output = agent_output_map.get(agent.id)
        if output and output.output_text:
            # 清理并格式化输出文本
            text = output.output_text
            # 确保 markdown 标题层级正确（将 ## 降级为 ###）
            text = text.replace("\n## ", "\n#### ")
            text = text.replace("\n# ", "\n### ")
            lines.append(text)
        else:
            lines.append("> 该 Agent 未生成有效分析。")
        lines.append("")

    # 语义相似度分析
    lines.append("---")
    lines.append("")
    lines.append("## 四、语义相似度分析")
    lines.append("")

    if task.similarity_results:
        lines.append("| Agent 1 | Agent 2 | 余弦相似度 | 说明 |")
        lines.append("|---------|---------|-----------|------|")
        for sr in task.similarity_results:
            name1 = agent_name_map.get(sr.agent_id_1, f"ID:{sr.agent_id_1}")
            name2 = agent_name_map.get(sr.agent_id_2, f"ID:{sr.agent_id_2}")
            level = "⚠️ 高度相似" if sr.similarity >= 0.7 else "✓ 差异明显"
            lines.append(
                f"| {name1} | {name2} | {sr.similarity:.2%} | {level} |"
            )
        lines.append("")

        for sr in task.similarity_results:
            if sr.explanation:
                lines.append(f"- {sr.explanation}")
        lines.append("")
    else:
        lines.append("> 未进行相似度分析或无有效数据。")
        lines.append("")

    # 冲突检测
    lines.append("---")
    lines.append("")
    lines.append("## 五、观点冲突检测")
    lines.append("")

    high_conflicts = [c for c in task.conflict_results if c.conflict_level == "high"]
    low_conflicts = [c for c in task.conflict_results if c.conflict_level == "low"]

    dim_name_map = {
        "benefit": "收益潜力", "cost": "成本可控性", "risk": "风险可控性",
        "tech": "技术可行性", "exec": "执行可行性", "long_term": "长期价值",
    }

    if task.conflict_results:
        lines.append("### 冲突维度总览")
        lines.append("")
        lines.append("| 维度 | 最高分 | 最低分 | 分差 | 冲突等级 |")
        lines.append("|------|-------|-------|-----|---------|")
        for cr in task.conflict_results:
            dim_cn = dim_name_map.get(cr.dimension, cr.dimension)
            diff = cr.max_score - cr.min_score
            level_emoji = "⚠️ 高冲突" if cr.conflict_level == "high" else "✓ 一致"
            lines.append(
                f"| {dim_cn} | {cr.max_score:.0f} | {cr.min_score:.0f} | {diff:.0f} | {level_emoji} |"
            )
        lines.append("")

        if high_conflicts:
            lines.append(f"### ⚠️ 高冲突维度（{len(high_conflicts)} 个）")
            lines.append("")
            for cr in high_conflicts:
                if cr.explanation:
                    lines.append(f"- {cr.explanation}")
            lines.append("")
    else:
        lines.append("> 未进行冲突检测或无有效数据。")
        lines.append("")

    # 综合建议
    lines.append("---")
    lines.append("")
    lines.append("## 六、综合建议")
    lines.append("")

    if task.final_summary:
        lines.append(task.final_summary)
    else:
        lines.append("> 未生成综合建议。")
    lines.append("")

    # 页脚
    lines.append("---")
    lines.append("")
    lines.append(
        f"*本报告由「可配置多智能体决策辅助系统」自动生成 "
        f"（任务 ID: {task.id}）*"
    )

    report_text = "\n".join(lines)

    # 生成安全的文件名（仅使用 ASCII 字符，HTTP Header 不支持中文）
    safe_name = f"decision_report_{task.id}.md"

    return PlainTextResponse(
        content=report_text,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={safe_name}",
        },
    )
