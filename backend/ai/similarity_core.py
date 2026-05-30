"""
语义相似度计算模块
-----------------
使用 sentence-transformers 将 Agent 输出文本转化为向量，
计算两两之间的余弦相似度，识别高度相似的观点对。
"""

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("similarity_core")

# ============================================================================
# 全局模型实例（懒加载，首次使用时自动下载）
# ============================================================================

# 使用轻量级 all-MiniLM-L6-v2 模型（约 80MB），适合课程项目环境
# 模型会将文本映射为 384 维向量
_embedding_model: Optional[SentenceTransformer] = None

# 相似度阈值：>= 此值视为高度相似
HIGH_SIMILARITY_THRESHOLD = 0.7

# 维度中文名映射
DIMENSION_NAMES = {
    "benefit": "收益潜力",
    "cost": "成本可控性",
    "risk": "风险可控性",
    "tech": "技术可行性",
    "exec": "执行可行性",
    "long_term": "长期价值",
}


def _get_model() -> SentenceTransformer:
    """
    获取（或初始化）全局 embedding 模型实例。

    首次调用时会自动下载模型文件，后续调用复用同一实例，
    避免重复加载带来的内存和时间开销。
    """
    global _embedding_model
    if _embedding_model is None:
        logger.info("正在加载 sentence-transformers 模型 (all-MiniLM-L6-v2)...")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("模型加载完成")
    return _embedding_model


# ============================================================================
# 相似度计算入口
# ============================================================================


def calculate_similarities(
    outputs: list,
    agent_name_map: dict[int, str] | None = None,
) -> list[dict]:
    """
    计算 Agent 输出两两之间的余弦相似度。

    对每个 Agent 的 output_text 进行向量化，
    然后计算所有不重复配对 (i, j) 的余弦相似度。

    参数:
        outputs: AgentOutput ORM 对象列表，每个对象需包含 id, task_id,
                 task_agent_id, output_text 属性
        agent_name_map: {agent_id: agent_name} 映射，用于生成解释文本

    返回:
        list[dict]: 相似度结果列表，每个元素包含:
            - task_id: int
            - agent_id_1: int
            - agent_id_2: int
            - similarity: float  (0~1)
            - explanation: str
    """
    if agent_name_map is None:
        agent_name_map = {}

    results: list[dict] = []

    # --- 过滤掉 output_text 为空的输出 ---
    valid_outputs = [o for o in outputs if o.output_text and o.output_text.strip()]

    if len(valid_outputs) < 2:
        logger.info("有效 Agent 输出少于 2 个，跳过相似度计算")
        return results

    # --- 向量化所有输出 ---
    try:
        model = _get_model()
        texts = [o.output_text[:2000] for o in valid_outputs]  # 截断前2000字符
        embeddings = model.encode(texts, show_progress_bar=False)
        logger.info(f"完成 {len(texts)} 个文本的向量化，维度: {embeddings.shape[1]}")
    except Exception as e:
        logger.error(f"文本向量化失败: {e}")
        return results

    # --- 计算两两余弦相似度 ---
    n = len(valid_outputs)
    for i in range(n):
        for j in range(i + 1, n):
            vec_i = embeddings[i]
            vec_j = embeddings[j]

            # 计算余弦相似度 = cos(theta) = (A·B) / (||A|| * ||B||)
            dot = np.dot(vec_i, vec_j)
            norm_i = np.linalg.norm(vec_i)
            norm_j = np.linalg.norm(vec_j)

            if norm_i == 0 or norm_j == 0:
                similarity = 0.0
            else:
                similarity = float(dot / (norm_i * norm_j))

            # 确保在 [0, 1] 范围内
            similarity = max(0.0, min(1.0, similarity))

            agent_i = valid_outputs[i]
            agent_j = valid_outputs[j]

            # 生成自然语言解释
            name_i = agent_name_map.get(agent_i.task_agent_id, f"Agent-{agent_i.task_agent_id}")
            name_j = agent_name_map.get(agent_j.task_agent_id, f"Agent-{agent_j.task_agent_id}")

            if similarity >= HIGH_SIMILARITY_THRESHOLD:
                explanation = (
                    f"「{name_i}」与「{name_j}」的观点高度相似"
                    f"（余弦相似度 {similarity:.2f}），建议检查是否存在观点重复。"
                )
                logger.info(
                    f"高相似度: {name_i} ↔ {name_j} = {similarity:.3f}"
                )
            else:
                explanation = (
                    f"「{name_i}」与「{name_j}」的观点相似度适中"
                    f"（余弦相似度 {similarity:.2f}），观点差异明显。"
                )

            results.append({
                "task_id": agent_i.task_id,
                "agent_id_1": agent_i.task_agent_id,
                "agent_id_2": agent_j.task_agent_id,
                "similarity": round(similarity, 4),
                "explanation": explanation,
            })

    logger.info(f"相似度计算完成: {len(results)} 对比较结果")
    return results
