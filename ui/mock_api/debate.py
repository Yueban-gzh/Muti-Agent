import json
import random
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

_mock_tasks_db: Dict[int, Dict] = {}
_task_counter = 1

# 默认权重（与文档一致）
DEFAULT_WEIGHTS = {
    "benefit": 0.2,
    "cost": 0.2,
    "risk": 0.2,
    "tech": 0.15,
    "exec": 0.15,
    "long_term": 0.1
}

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def _generate_score_json() -> str:
    scores = {k: random.randint(1, 10) for k in DEFAULT_WEIGHTS.keys()}
    return json.dumps(scores)

def _calculate_weighted_ranking(outputs: List[Dict], weight_config: Optional[str] = None) -> List[Dict]:
    if weight_config:
        try:
            weights = json.loads(weight_config)
        except:
            weights = DEFAULT_WEIGHTS.copy()
    else:
        weights = DEFAULT_WEIGHTS.copy()
    
    ranking = []
    for out in outputs:
        try:
            scores = json.loads(out["score_json"])
        except:
            scores = {k: 0 for k in DEFAULT_WEIGHTS}
        total = 0.0
        available = True
        for dim, w in weights.items():
            score = scores.get(dim, 0)
            if score == 0:
                available = False
            total += score * w
        ranking.append({
            "task_agent_id": out["task_agent_id"],
            "agent_name": out["agent_name"],
            "scores": scores,
            "total_score": round(total, 2),
            "rank": None,
            "score_available": available
        })
    ranking.sort(key=lambda x: x["total_score"], reverse=True)
    for idx, item in enumerate(ranking):
        item["rank"] = idx + 1
    return ranking

def create_task(data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    global _task_counter
    task_id = _task_counter
    _task_counter += 1
    task = {
        "task_id": task_id,
        "user_id": user_id,
        "question": data["question"],
        "decision_mode": data["decision_mode"],
        "agent_count": data["agent_count"],
        "weight_config": data.get("weight_config"),
        "status": "pending",
        "error_message": None,
        "created_at": _utcnow_iso(),
        "agents": data["agents"]
    }
    _mock_tasks_db[task_id] = task
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "任务已提交，正在后台处理"
    }

def get_task_status(task_id: int) -> Optional[Dict[str, Any]]:
    task = _mock_tasks_db.get(task_id)
    if not task:
        return None
    return {"task_id": task_id, "status": task["status"]}

def get_task_result(task_id: int) -> Optional[Dict[str, Any]]:
    task = _mock_tasks_db.get(task_id)
    if not task:
        return None

    # 模拟处理过程
    if task["status"] == "pending":
        task["status"] = "processing"
    if task["status"] == "processing":
        task["status"] = "completed"

    agents = []
    outputs = []
    for idx, agent in enumerate(task["agents"], start=1):
        agents.append({
            "id": idx,
            "task_id": task_id,
            "agent_name": agent["agent_name"],
            "role_description": agent["role_description"],
            "focus_area": agent["focus_area"],
            "tone": agent["tone"],
            "final_prompt": f"你是{agent['agent_name']}，请分析问题"
        })
        score_json = _generate_score_json()
        outputs.append({
            "id": idx,
            "task_id": task_id,
            "task_agent_id": idx,
            "agent_name": agent["agent_name"],
            "output_text": f"## 观点摘要\n{agent['agent_name']} 对该问题进行了分析。\n\n## 理由\n...",
            "score_json": score_json,
            "created_at": _utcnow_iso()
        })

    # 加权排名
    weighted_ranking = _calculate_weighted_ranking(outputs, task.get("weight_config"))

    # 相似度矩阵（随机生成，仅当 Agent >=2）
    similarities = []
    agent_ids = [a["id"] for a in agents]
    if len(agent_ids) >= 2:
        for i in range(len(agent_ids)):
            for j in range(i+1, len(agent_ids)):
                sim = round(random.uniform(0.3, 0.98), 4)
                similarities.append({
                    "id": len(similarities) + 1,
                    "task_id": task_id,
                    "agent_id_1": agent_ids[i],
                    "agent_id_2": agent_ids[j],
                    "similarity": sim,
                    "explanation": f"{agents[i]['agent_name']} 与 {agents[j]['agent_name']} 的相似度为 {sim}",
                    "created_at": _utcnow_iso()
                })

    # 冲突检测（随机生成）
    conflicts = []
    dims = list(DEFAULT_WEIGHTS.keys())
    for dim in dims:
        if random.random() > 0.6:  # 约40%概率生成冲突
            max_score = random.randint(7, 10)
            min_score = random.randint(1, 4)
            conflicts.append({
                "id": len(conflicts) + 1,
                "task_id": task_id,
                "dimension": dim,
                "max_score": max_score,
                "min_score": min_score,
                "conflict_level": "high" if (max_score - min_score) >= 4 else "low",
                "explanation": f"在维度「{dim}」上，最高分 {max_score} 与最低分 {min_score} 差距较大，存在明显冲突。",
                "created_at": _utcnow_iso()
            })

    return {
        "task_id": task_id,
        "question": task["question"],
        "decision_mode": task["decision_mode"],
        "agent_count": task["agent_count"],
        "weight_config": task.get("weight_config"),
        "status": "completed",
        "error_message": None,
        "final_summary": "# 综合建议\n经过多角度分析，建议您结合自身情况谨慎决策。",
        "created_at": task["created_at"],
        "agents": agents,
        "outputs": outputs,
        "similarities": similarities,
        "conflicts": conflicts,
        "weighted_ranking": weighted_ranking
    }