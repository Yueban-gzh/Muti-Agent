"""讨论纪要：LLM 压缩为主，规则拼接兜底。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.config import (
    DISCUSS_INPUT_MAX_CHARS,
    DISCUSSION_SUMMARY_MAX_NEW_TOKENS,
    DISCUSSION_SUMMARY_TARGET_CHARS,
    SUMMARY_LLM_TEMPERATURE,
)
from ai.llm.chat import llm_chat

if TYPE_CHECKING:
    from db.models import DecisionTask, DiscussionMessage, TaskAgent

logger = logging.getLogger("discussion_summary")

SUMMARY_SYSTEM = """你是决策会议书记员。请根据以下多轮讨论记录，写一份客观、结构化的讨论纪要。
要求：
1. 总长度控制在 800 字以内（中文）；
2. 必须单独列出「用户（决策方）的主要观点、约束与倾向」；
3. 分别归纳支持方、反对方、评审方（如有）的核心论点；
4. 列出 2～5 条「尚未达成一致的分歧」；
5. 不要给最终决策建议，不要输出 JSON 评分。"""


def _stance_tag(stance: str | None) -> str:
    from ai.prompts.debate_exchange import stance_label

    return stance_label(stance)


def format_transcript(
    task: "DecisionTask",
    messages: list["DiscussionMessage"],
    agents_by_id: dict[int, "TaskAgent"],
) -> str:
    lines = [
        f"【决策问题】{task.question}",
        f"【背景说明】{task.context_notes or '无'}",
        "",
        "【讨论记录】",
    ]
    for msg in messages:
        if msg.role == "user":
            lines.append(f"[用户] {msg.content}")
        elif msg.role == "agent" and msg.task_agent_id:
            agent = agents_by_id.get(msg.task_agent_id)
            if agent:
                from ai.prompts.debate_exchange import agent_display_name

                label = agent_display_name(agent.agent_name, agent.stance)
                lines.append(f"[{label}] {msg.content[:400]}")
            else:
                lines.append(f"[Agent] {msg.content[:400]}")
        elif msg.role == "system":
            lines.append(f"[系统] {msg.content[:200]}")

    text = "\n".join(lines)
    if len(text) > DISCUSS_INPUT_MAX_CHARS:
        text = text[:DISCUSS_INPUT_MAX_CHARS] + "\n…（讨论记录已截断）"
    return text


def build_rule_fallback_summary(
    task: "DecisionTask",
    messages: list["DiscussionMessage"],
    agents_by_id: dict[int, "TaskAgent"],
) -> str:
    parts = [
        f"【决策问题】{task.question}",
        f"【背景】{task.context_notes or '无'}",
        "【用户发言摘录】",
    ]
    user_lines = [m.content[:300] for m in messages if m.role == "user"]
    parts.extend(user_lines[:10] or ["（无）"])
    parts.append("【各方观点摘录】")
    for msg in messages:
        if msg.role != "agent" or not msg.task_agent_id:
            continue
        agent = agents_by_id.get(msg.task_agent_id)
        name = agent.agent_name if agent else "Agent"
        parts.append(f"- {name}: {msg.content[:200]}")
    text = "\n".join(parts)
    return text[:DISCUSSION_SUMMARY_TARGET_CHARS + 200]


async def build_discussion_summary_llm(
    task: "DecisionTask",
    messages: list["DiscussionMessage"],
    agents_by_id: dict[int, "TaskAgent"],
    *,
    task_id: int,
) -> tuple[str, str]:
    """返回 (summary_text, method)。method: llm | rule_fallback"""
    if not messages:
        return (
            f"【决策问题】{task.question}\n（讨论区暂无消息，请结合背景直接分析。）",
            "rule_fallback",
        )

    transcript = format_transcript(task, messages, agents_by_id)
    result = await llm_chat(
        SUMMARY_SYSTEM,
        transcript,
        temperature=SUMMARY_LLM_TEMPERATURE,
        max_new_tokens=DISCUSSION_SUMMARY_MAX_NEW_TOKENS,
        task_id=task_id,
        label="discussion_summary",
    )
    if result.get("success") and result.get("text"):
        text = result["text"].strip()
        if len(text) > DISCUSSION_SUMMARY_TARGET_CHARS + 300:
            text = text[: DISCUSSION_SUMMARY_TARGET_CHARS + 300]
        return text, "llm"

    logger.warning("LLM 纪要失败，使用规则兜底: %s", result.get("error"))
    return build_rule_fallback_summary(task, messages, agents_by_id), "rule_fallback"
