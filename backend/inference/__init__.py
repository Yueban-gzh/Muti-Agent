"""
Jixia Inference Engine — 自研轻量推理引擎

基于 transformers 原生 HunYuanDenseV1ForCausalLM 支持，
针对 RTX 3090 + GPTQ-INT4 优化。

优化手段:
  - Flash Attention (torch SDPA 自动启用)
  - torch.compile 全模型编译 (reduce-overhead)
  - 连续批处理 (权重共享，分摊显存带宽)
  - DynamicCache 管理 KV Cache
  - Top-p (nucleus) sampling
  - SSE 流式输出 (OpenAI 兼容)
  - Async bridge (asyncio + 后台引擎线程)

文件:
  config.py   — 配置 dataclass
  kvcache.py  — KV Cache 池 + Prefix Cache (Radix Tree)
  engine.py   — 推理引擎核心 (模型加载、prefill/decode、采样)
  server.py   — FastAPI + OpenAI 兼容端点
  cli.py      — 启动入口 + 远程脚本生成
"""

from backend.inference.config import ServerConfig, EngineConfig
from backend.inference.engine import InferenceEngine, GenerationRequest

__all__ = [
    "ServerConfig",
    "EngineConfig",
    "InferenceEngine",
    "GenerationRequest",
]
