"""
推理引擎配置。
"""

from dataclasses import dataclass, field
from typing import Optional
import torch


@dataclass
class ServerConfig:
    """OpenAI 兼容 API 服务配置。"""

    host: str = "0.0.0.0"
    port: int = 30000

    # 模型
    model_path: str = "/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4"
    model_name: str = "Hunyuan-7B-Instruct-GPTQ-Int4"

    # 并发
    max_batch_size: int = 32  # 单 batch 最大请求数，32 个头同时解码
    max_waiting_requests: int = 128  # 等待队列上限
    batch_timeout_ms: float = 50.0  # 收集 batch 的等待窗口（ms）

    # 生成默认值
    default_max_tokens: int = 1024
    default_temperature: float = 0.7
    default_top_p: float = 0.9

    # 日志
    log_level: str = "info"

    # 显存限制
    gpu_memory_fraction: float = 0.92


@dataclass
class EngineConfig:
    """推理引擎配置。"""

    model_path: str = "/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4"
    dtype: torch.dtype = torch.float16
    device: str = "cuda"

    # 序列长度
    max_seq_len: int = 4096  # 单序列最大长度
    max_model_len: int = 16384  # 模型原生上下文长度（用于 rope 配置）

    # KV Cache 池
    kv_cache_total_tokens: int = 32768  # 预分配 token 总数 (~4.3GB for Hunyuan 7B GQA)

    # 批处理
    max_batch_size: int = 32
    batch_timeout_ms: float = 50.0  # 收集 batch 的等待窗口（ms）

    # torch.compile
    use_torch_compile: bool = True
    torch_compile_mode: str = "reduce-overhead"  # "default" | "reduce-overhead" | "max-autotune"

    # CUDA Graph (decode 阶段)
    use_cuda_graph: bool = True
    cuda_graph_max_batch_size: int = 32

    # Prefix Cache
    use_prefix_cache: bool = True
    prefix_cache_max_entries: int = 64  # 最多缓存 64 个前缀

    # 预热
    warmup: bool = True


def default_server_config() -> ServerConfig:
    return ServerConfig()


def default_engine_config() -> EngineConfig:
    return EngineConfig()
