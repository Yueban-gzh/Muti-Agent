"""讨论交流期业务逻辑。"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm.chat import llm_chat
from ai.prompts.debate_exchange import (
    agent_display_name,
    build_agent_only_con_message,
    build_agent_only_judge_message,
    build_agent_only_pro_message,
    build_con_user_message,
    build_debate_system_prompt,
    build_debate_welcome,
    build_judge_user_message,
    build_pro_user_message,
    stance_label,
)
from ai.prompts.persona import build_discuss_system_prompt, build_discuss_user_message
from core.config import (
    DISCUSS_HISTORY_MAX_MESSAGES,
    DISCUSS_INPUT_MAX_CHARS,
    DISCUSS_MAX_NEW_TOKENS,
    MAX_DEBATE_EXCHANGE_ROUNDS,
    MAX_DISCUSSION_USER_TURNS,
    MAX_USER_MESSAGE_CHARS,
)
from db.models import DecisionTask, DiscussionMessage, TaskAgent, User
from schemas.discussion import DiscussionMessageCreate
from services.exceptions import ServiceError
from services.log_constants import TASK_DISCUSS_MESSAGE
from services.log_service import append_log

logger = logging.getLogger("discussion_service")

WELCOME_TEMPLATE = (
    "欢迎进入决策讨论室。决策问题：{question}\n"
    "参与专家：{agents}\n"
    "请陈述你的观点、约束或追问。"
)


class DiscussionService:
    @staticmethod
    def ensure_discussing(task: DecisionTask, user: User) -> None:
        from services.task_service import TaskService

        TaskService.ensure_task_access(task, user)
        if task.status != "discussing":
            raise ServiceError(
                f"当前任务状态为 {task.status}，仅 discussing 阶段可发送消息",
                status_code=400,
            )

    @staticmethod
    async def _next_seq(db: AsyncSession, task_id: int) -> int:
        result = await db.execute(
            select(func.max(DiscussionMessage.seq)).where(
                DiscussionMessage.task_id == task_id
            )
        )
        current = result.scalar()
        return (current or 0) + 1

    @staticmethod
    async def ensure_welcome_message(
        db: AsyncSession, task: DecisionTask, agents: list[TaskAgent]
    ) -> None:
        result = await db.execute(
            select(DiscussionMessage.id)
            .where(DiscussionMessage.task_id == task.id)
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return

        if task.decision_mode == "debate":
            content = build_debate_welcome(task.question, agents)
        else:
            names = "、".join(
                agent_display_name(a.agent_name, a.stance) for a in agents
            )
            content = WELCOME_TEMPLATE.format(question=task.question, agents=names)

        seq = await DiscussionService._next_seq(db, task.id)
        db.add(
            DiscussionMessage(
                task_id=task.id,
                seq=seq,
                role="system",
                content=content,
            )
        )
        await db.commit()

    @staticmethod
    def _agents_for_scope(agents: list[TaskAgent], scope: str) -> list[TaskAgent]:
        """非辩论交流期仅使用 all_brief（全体专家各一条）。"""
        if scope != "all_brief":
            raise ServiceError(f"非辩论模式仅支持 reply_scope=all_brief，当前为 {scope}")
        return agents

    @staticmethod
    def _agent_meta(agent: TaskAgent | None) -> dict:
        if not agent:
            return {
                "agent_name": None,
                "stance": None,
                "stance_label": None,
                "agent_display_name": None,
            }
        return {
            "agent_name": agent.agent_name,
            "stance": agent.stance,
            "stance_label": stance_label(agent.stance),
            "agent_display_name": agent_display_name(agent.agent_name, agent.stance),
        }

    @staticmethod
    def _to_response(
        msg: DiscussionMessage,
        agent: TaskAgent | None = None,
    ) -> dict:
        meta = DiscussionService._agent_meta(agent)
        return {
            "id": msg.id,
            "task_id": msg.task_id,
            "seq": msg.seq,
            "role": msg.role,
            "task_agent_id": msg.task_agent_id,
            "target_agent_id": msg.target_agent_id,
            "reply_scope": msg.reply_scope,
            "content": msg.content,
            "created_at": msg.created_at,
            **meta,
        }

    @staticmethod
    async def _load_room_messages(
        db: AsyncSession, task_id: int, before_seq: int | None = None
    ) -> list[DiscussionMessage]:
        q = select(DiscussionMessage).where(DiscussionMessage.task_id == task_id)
        if before_seq is not None:
            q = q.where(DiscussionMessage.seq < before_seq)
        result = await db.execute(q.order_by(DiscussionMessage.seq))
        return list(result.scalars().all())

    @staticmethod
    def _format_room_transcript(
        messages: list[DiscussionMessage],
        agents_by_id: dict[int, TaskAgent],
        *,
        max_messages: int | None = None,
    ) -> str:
        cap = max_messages if max_messages is not None else DISCUSS_HISTORY_MAX_MESSAGES
        lines: list[str] = []
        for msg in messages:
            if msg.role == "user":
                lines.append(f"[用户/决策方] {msg.content}")
            elif msg.role == "agent" and msg.task_agent_id:
                agent = agents_by_id.get(msg.task_agent_id)
                if agent:
                    label = agent_display_name(agent.agent_name, agent.stance)
                    lines.append(f"[{label}] {msg.content}")
                else:
                    lines.append(f"[辩手] {msg.content}")
            elif msg.role == "system":
                continue
        if cap > 0 and len(lines) > cap:
            omitted = len(lines) - cap
            lines = [f"…（更早 {omitted} 条记录已省略）", *lines[-cap:]]
        return "\n".join(lines)

    @staticmethod
    def _truncate_discuss_prompt(text: str) -> str:
        if len(text) <= DISCUSS_INPUT_MAX_CHARS:
            return text
        logger.warning(
            "讨论 prompt 超长 (%s > %s)，已截断尾部上下文",
            len(text),
            DISCUSS_INPUT_MAX_CHARS,
        )
        head = "【提示】讨论记录过长，仅保留最近部分内容。\n\n"
        budget = DISCUSS_INPUT_MAX_CHARS - len(head)
        return head + text[-budget:]

    @staticmethod
    async def _generate_agent_line(
        db: AsyncSession,
        task: DecisionTask,
        agent: TaskAgent,
        user_prompt: str,
        reply_scope: str,
    ) -> DiscussionMessage:
        user_prompt = DiscussionService._truncate_discuss_prompt(user_prompt)

        if task.decision_mode == "debate":
            system = build_debate_system_prompt(
                agent, task.decision_mode, task.question, task.context_notes
            )
        else:
            system = build_discuss_system_prompt(
                agent_name=agent.agent_name,
                role_description=agent.role_description,
                focus_area=agent.focus_area,
                tone=agent.tone,
                stance=agent.stance,
                extra_notes=agent.extra_notes,
                decision_mode=task.decision_mode,
                question=task.question,
                context_notes=task.context_notes,
            )

        result = await llm_chat(
            system,
            user_prompt,
            max_new_tokens=DISCUSS_MAX_NEW_TOKENS,
            temperature=0.75,
            task_id=task.id,
            label=f"discuss:{agent.stance}:{agent.agent_name}",
        )
        text = (result.get("text") or "").strip() if result.get("success") else ""
        if not text:
            text = f"[回复生成失败] {result.get('error', '未知错误')}"

        seq = await DiscussionService._next_seq(db, task.id)
        record = DiscussionMessage(
            task_id=task.id,
            seq=seq,
            role="agent",
            task_agent_id=agent.id,
            reply_scope=reply_scope,
            content=text,
        )
        db.add(record)
        await db.flush()
        return record

    @staticmethod
    async def _run_debate_round(
        db: AsyncSession,
        task: DecisionTask,
        agents: list[TaskAgent],
        user_content: str,
        user_seq: int,
    ) -> list[DiscussionMessage]:
        """支持方 → 反对方反驳 → 评审归纳（与用户发言绑定的一轮交锋）。"""
        agents_by_id = {a.id: a for a in agents}
        room_before = await DiscussionService._load_room_messages(db, task.id, user_seq)
        transcript = DiscussionService._format_room_transcript(room_before, agents_by_id)

        pros = [a for a in agents if a.stance == "pro"]
        cons = [a for a in agents if a.stance == "con"]
        judges = [a for a in agents if a.stance == "judge"]

        if not pros or not cons:
            raise ServiceError("辩论交锋需要至少一名支持方与一名反对方")

        records: list[DiscussionMessage] = []
        pro_last: str | None = None
        con_last: str | None = None

        for pro in pros[:1]:
            prompt = build_pro_user_message(user_content, transcript)
            rec = await DiscussionService._generate_agent_line(
                db, task, pro, prompt, "debate_round"
            )
            records.append(rec)
            pro_last = rec.content
            transcript = DiscussionService._format_room_transcript(
                room_before + records, agents_by_id
            )

        for con in cons[:1]:
            prompt = build_con_user_message(user_content, transcript, pro_last)
            rec = await DiscussionService._generate_agent_line(
                db, task, con, prompt, "debate_round"
            )
            records.append(rec)
            con_last = rec.content

        for judge in judges[:1]:
            prompt = build_judge_user_message(
                user_content, transcript, pro_last, con_last
            )
            rec = await DiscussionService._generate_agent_line(
                db, task, judge, prompt, "debate_round"
            )
            records.append(rec)

        return records

    @staticmethod
    async def _get_last_user_content(
        db: AsyncSession, task_id: int, fallback: str
    ) -> str:
        result = await db.execute(
            select(DiscussionMessage)
            .where(
                DiscussionMessage.task_id == task_id,
                DiscussionMessage.role == "user",
            )
            .order_by(DiscussionMessage.seq.desc())
            .limit(1)
        )
        msg = result.scalar_one_or_none()
        return msg.content if msg else fallback

    @staticmethod
    async def _run_agent_exchange_round(
        db: AsyncSession,
        task: DecisionTask,
        agents: list[TaskAgent],
    ) -> tuple[DiscussionMessage | None, list[DiscussionMessage]]:
        """用户不发言，辩手继续交锋一轮。"""
        agents_by_id = {a.id: a for a in agents}
        room = await DiscussionService._load_room_messages(db, task.id)
        transcript = DiscussionService._format_room_transcript(room, agents_by_id)

        pros = [a for a in agents if a.stance == "pro"]
        cons = [a for a in agents if a.stance == "con"]
        judges = [a for a in agents if a.stance == "judge"]
        if not pros or not cons:
            raise ServiceError("辩论交锋需要至少一名支持方与一名反对方")

        n = (task.debate_exchange_rounds or 0) + 1
        seq = await DiscussionService._next_seq(db, task.id)
        system_msg = DiscussionMessage(
            task_id=task.id,
            seq=seq,
            role="system",
            content=f"── 辩手继续交锋（第 {n} 轮，决策方本轮不发言）──",
            reply_scope="agent_exchange",
        )
        db.add(system_msg)
        await db.flush()

        records: list[DiscussionMessage] = []
        pro_last: str | None = None
        con_last: str | None = None
        acc = room + [system_msg]

        for pro in pros[:1]:
            con_last_msg = None
            for m in reversed(acc):
                if m.role == "agent" and m.task_agent_id:
                    ag = agents_by_id.get(m.task_agent_id)
                    if ag and ag.stance == "con":
                        con_last_msg = m.content
                        break
            prompt = build_agent_only_pro_message(
                DiscussionService._format_room_transcript(acc, agents_by_id),
                con_last_msg,
            )
            rec = await DiscussionService._generate_agent_line(
                db, task, pro, prompt, "agent_exchange"
            )
            records.append(rec)
            pro_last = rec.content
            acc = acc + records

        for con in cons[:1]:
            prompt = build_agent_only_con_message(
                DiscussionService._format_room_transcript(acc, agents_by_id),
                pro_last,
            )
            rec = await DiscussionService._generate_agent_line(
                db, task, con, prompt, "agent_exchange"
            )
            records.append(rec)
            con_last = rec.content
            acc = acc + [rec]

        for judge in judges[:1]:
            prompt = build_agent_only_judge_message(
                DiscussionService._format_room_transcript(acc, agents_by_id),
                pro_last,
                con_last,
            )
            rec = await DiscussionService._generate_agent_line(
                db, task, judge, prompt, "agent_exchange"
            )
            records.append(rec)

        task.debate_exchange_rounds = n
        return system_msg, records

    @staticmethod
    async def run_agent_exchange(
        db: AsyncSession,
        task: DecisionTask,
        user: User,
    ) -> dict:
        """辩手自主交锋（用户不发言）。"""
        DiscussionService.ensure_discussing(task, user)
        if task.decision_mode != "debate":
            raise ServiceError("仅辩论模式可发起辩手自主交锋", status_code=400)
        if (task.debate_exchange_rounds or 0) >= MAX_DEBATE_EXCHANGE_ROUNDS:
            raise ServiceError(
                f"辩手自主交锋已达上限（{MAX_DEBATE_EXCHANGE_ROUNDS} 轮），请发言或生成正式分析"
            )

        agents_result = await db.execute(
            select(TaskAgent)
            .where(TaskAgent.task_id == task.id)
            .order_by(TaskAgent.sort_order)
        )
        agents = list(agents_result.scalars().all())
        agents_by_id = {a.id: a for a in agents}

        system_msg, agent_records = await DiscussionService._run_agent_exchange_round(
            db, task, agents
        )
        await db.commit()
        if system_msg:
            await db.refresh(system_msg)
        for r in agent_records:
            await db.refresh(r)

        await append_log(
            TASK_DISCUSS_MESSAGE,
            f"任务 {task.id} 辩手自主交锋第 {task.debate_exchange_rounds} 轮",
            user_id=user.id,
        )

        return {
            "system_message": DiscussionService._to_response(system_msg),
            "agent_messages": [
                DiscussionService._to_response(r, agents_by_id.get(r.task_agent_id))
                for r in agent_records
            ],
            "debate_exchange_round": task.debate_exchange_rounds,
            "step_type": "agent_exchange",
        }

    @staticmethod
    async def _reply_as_agent_to_user(
        db: AsyncSession,
        task: DecisionTask,
        agent: TaskAgent,
        user_content: str,
        reply_scope: str,
        *,
        user_seq: int,
        agents_by_id: dict[int, TaskAgent],
    ) -> DiscussionMessage:
        """非辩论模式：加载本轮用户消息之前的讨论记录，再生成回复。"""
        room_before = await DiscussionService._load_room_messages(
            db, task.id, user_seq
        )
        transcript = DiscussionService._format_room_transcript(
            room_before, agents_by_id
        )
        user_msg = build_discuss_user_message(user_content, transcript)
        return await DiscussionService._generate_agent_line(
            db, task, agent, user_msg, reply_scope
        )

    @staticmethod
    async def post_message(
        db: AsyncSession,
        task: DecisionTask,
        user: User,
        data: DiscussionMessageCreate,
    ) -> dict:
        DiscussionService.ensure_discussing(task, user)
        if task.discussion_turns >= MAX_DISCUSSION_USER_TURNS:
            raise ServiceError(
                f"已达讨论上限（{MAX_DISCUSSION_USER_TURNS} 轮），请生成正式分析"
            )
        content = data.content.strip()
        if len(content) > MAX_USER_MESSAGE_CHARS:
            raise ServiceError(f"消息过长，最多 {MAX_USER_MESSAGE_CHARS} 字")

        agents_result = await db.execute(
            select(TaskAgent)
            .where(TaskAgent.task_id == task.id)
            .order_by(TaskAgent.sort_order)
        )
        agents = list(agents_result.scalars().all())
        agents_by_id = {a.id: a for a in agents}
        await DiscussionService.ensure_welcome_message(db, task, agents)

        scope = data.reply_scope
        if task.decision_mode == "debate":
            # 辩论交流期统一为一轮完整交锋，不支持「只问某一方」
            if scope != "debate_round":
                scope = "debate_round"
        else:
            # 非辩论模式：全体专家各回复一条
            if scope != "all_brief":
                scope = "all_brief"

        seq = await DiscussionService._next_seq(db, task.id)
        user_msg = DiscussionMessage(
            task_id=task.id,
            seq=seq,
            role="user",
            content=content,
            target_agent_id=data.target_agent_id,
            reply_scope=scope,
        )
        db.add(user_msg)
        task.discussion_turns += 1
        await db.flush()

        agent_records: list[DiscussionMessage] = []

        if task.decision_mode == "debate" and scope == "debate_round":
            agent_records = await DiscussionService._run_debate_round(
                db, task, agents, content, user_msg.seq
            )
        else:
            targets = DiscussionService._agents_for_scope(agents, scope)
            if not targets:
                raise ServiceError("当前回复范围内没有可用的 Agent")
            if scope == "all_brief" and len(targets) > 3:
                raise ServiceError("全体回复模式下 Agent 数量不能超过 3")
            for agent in targets:
                rec = await DiscussionService._reply_as_agent_to_user(
                    db,
                    task,
                    agent,
                    content,
                    scope,
                    user_seq=user_msg.seq,
                    agents_by_id=agents_by_id,
                )
                agent_records.append(rec)

        await db.commit()
        await db.refresh(user_msg)
        for r in agent_records:
            await db.refresh(r)

        await append_log(
            TASK_DISCUSS_MESSAGE,
            f"任务 {task.id} 用户发言 scope={scope}，{len(agent_records)} 条辩手回复",
            user_id=user.id,
        )

        step_type = "user_debate_round" if (
            task.decision_mode == "debate" and scope == "debate_round"
        ) else "user_message"

        return {
            "user_message": DiscussionService._to_response(user_msg),
            "agent_messages": [
                DiscussionService._to_response(
                    r, agents_by_id.get(r.task_agent_id)
                )
                for r in agent_records
            ],
            "debate_round": task.decision_mode == "debate" and scope == "debate_round",
            "step_type": step_type,
            "system_message": None,
        }

    @staticmethod
    async def list_messages(
        db: AsyncSession,
        task: DecisionTask,
        user: User,
        *,
        after_seq: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        from services.task_service import TaskService

        TaskService.ensure_task_access(task, user)
        result = await db.execute(
            select(DiscussionMessage)
            .where(
                DiscussionMessage.task_id == task.id,
                DiscussionMessage.seq > after_seq,
            )
            .order_by(DiscussionMessage.seq)
            .limit(min(limit, 200))
        )
        messages = list(result.scalars().all())
        agents_result = await db.execute(
            select(TaskAgent).where(TaskAgent.task_id == task.id)
        )
        agents_by_id = {a.id: a for a in agents_result.scalars().all()}
        return [
            DiscussionService._to_response(
                m, agents_by_id.get(m.task_agent_id) if m.role == "agent" else None
            )
            for m in messages
        ]

    @staticmethod
    async def get_debate_roster(
        db: AsyncSession, task: DecisionTask, user: User
    ) -> list[dict]:
        """返回辩手席位表（含立场），供前端展示。"""
        from services.task_service import TaskService

        TaskService.ensure_task_access(task, user)
        result = await db.execute(
            select(TaskAgent)
            .where(TaskAgent.task_id == task.id)
            .order_by(TaskAgent.sort_order)
        )
        roster = []
        for a in result.scalars().all():
            roster.append(
                {
                    "task_agent_id": a.id,
                    "agent_name": a.agent_name,
                    "stance": a.stance,
                    "stance_label": stance_label(a.stance),
                    "agent_display_name": agent_display_name(a.agent_name, a.stance),
                    "role_description": a.role_description,
                }
            )
        return roster
