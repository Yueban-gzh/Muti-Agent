"""
推理引擎核心 — 基于 transformers model.generate()，可靠稳定。

架构:
  FastAPI (async) ←→ InferenceEngine (后台线程)
                         ↑
                    queue.Queue 桥接
"""

from __future__ import annotations

import time
import logging
import threading
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Callable, Dict, List, Optional, Tuple

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    PreTrainedModel,
    PreTrainedTokenizer,
)

from backend.inference.config import EngineConfig

logger = logging.getLogger(__name__)


@dataclass
class GenerationRequest:
    request_id: str
    prompt: str
    token_ids: List[int] = field(default_factory=list)
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    stop_sequences: List[str] = field(default_factory=list)

    # 运行时
    generated_ids: List[int] = field(default_factory=list)
    finished: bool = False
    finish_reason: str = ""

    # 统计
    created_at: float = 0.0
    first_token_at: Optional[float] = None


class InferenceEngine:
    """核心推理引擎 — 使用 model.generate() 保证兼容性。"""

    def __init__(self, config: EngineConfig):
        self.config = config
        self.model: Optional[PreTrainedModel] = None
        self.tokenizer: Optional[PreTrainedTokenizer] = None

        self._request_queue: Queue = Queue()
        self._callbacks: Dict[str, Callable] = {}
        self._engine_thread: Optional[threading.Thread] = None
        self._running = False

    # ── 初始化 ──────────────────────────

    def initialize(self):
        logger.info(f"Loading model from {self.config.model_path}...")
        t0 = time.time()

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.config.model_path, trust_remote_code=True, padding_side="left",
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            self.config.model_path,
            torch_dtype=self.config.dtype,
            device_map=self.config.device,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        self.model.eval()

        elapsed = time.time() - t0
        params_b = sum(p.numel() for p in self.model.parameters()) / 1e9
        mem_gb = torch.cuda.max_memory_allocated() / 1e9
        logger.info(f"Model loaded in {elapsed:.1f}s. Params: {params_b:.2f}B, Mem: {mem_gb:.2f}GB")

        # 不 compile — Hunyuan 模型有动态 graph break 问题

        if self.config.warmup:
            self._warmup()

    def _warmup(self):
        logger.info("Warming up...")
        t0 = time.time()
        dummy = self.tokenizer.encode("Hello", return_tensors="pt").to(self.config.device)
        with torch.inference_mode():
            _ = self.model.generate(dummy, max_new_tokens=4, do_sample=False, pad_token_id=self.tokenizer.eos_token_id)
        torch.cuda.synchronize()
        logger.info(f"Warmup done in {time.time() - t0:.1f}s")

    # ── 请求接口 ────────────────────────

    def submit(self, request: GenerationRequest, callback: Callable):
        request.created_at = time.time()
        request.token_ids = self.tokenizer.encode(request.prompt, add_special_tokens=False)
        self._request_queue.put(request)
        self._callbacks[request.request_id] = callback

    # ── 生命周期 ────────────────────────

    def start(self):
        self._running = True
        self._engine_thread = threading.Thread(target=self._engine_loop, daemon=True, name="engine")
        self._engine_thread.start()
        logger.info("Engine started")

    def stop(self):
        self._running = False
        if self._engine_thread:
            self._engine_thread.join(timeout=10)

    # ── 主循环 ──────────────────────────

    def _engine_loop(self):
        while self._running:
            try:
                req = self._request_queue.get(timeout=0.5)
            except Empty:
                continue

            # 单请求处理（简单可靠）
            try:
                self._process_single(req)
            except Exception as e:
                logger.error(f"Request {req.request_id} error: {e}", exc_info=True)
                self._finish_request(req, "error")

    def _process_single(self, req: GenerationRequest):
        """用 model.generate() 处理单个请求。"""
        inputs = self.tokenizer(
            req.prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.config.max_seq_len - req.max_tokens,
        ).to(self.config.device)

        input_len = inputs.input_ids.shape[1]

        # 构建 generate 参数
        gen_kwargs = dict(
            max_new_tokens=req.max_tokens,
            do_sample=req.temperature > 0,
            temperature=req.temperature if req.temperature > 0 else 1.0,
            top_p=req.top_p,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
            use_cache=True,
        )

        # 流式生成 — 用 generate + streamer
        from transformers import TextStreamer, TextIteratorStreamer
        from threading import Thread

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=60,
        )

        gen_kwargs["streamer"] = streamer
        gen_kwargs["input_ids"] = inputs.input_ids
        gen_kwargs["attention_mask"] = inputs.attention_mask

        # 在子线程中运行 generate（streamer 需要）
        def generate_thread():
            with torch.inference_mode():
                self.model.generate(**gen_kwargs)

        t = Thread(target=generate_thread, daemon=True)
        t.start()

        # 从 streamer 逐 token 读取并回调
        token_count = 0
        for token_text in streamer:
            if not token_text:
                continue
            token_count += 1
            req.generated_ids.append(0)  # placeholder — streamer gives text, not ids
            if req.first_token_at is None:
                req.first_token_at = time.time()
            self._emit_token(req, token_text)

            if token_count >= req.max_tokens:
                req.finish_reason = "length"
                break

        t.join(timeout=10)
        if not req.finish_reason:
            req.finish_reason = "stop"
        self._finish_request(req, req.finish_reason)

    # ── 回调 ────────────────────────────

    def _emit_token(self, request: GenerationRequest, token_text: str):
        cb = self._callbacks.get(request.request_id)
        if cb:
            try:
                cb(request, token_text, 0)
            except Exception:
                pass

    def _finish_request(self, request: GenerationRequest, reason: str):
        request.finished = True
        request.finish_reason = reason
        # 发送完成信号
        cb = self._callbacks.pop(request.request_id, None)
        if cb:
            try:
                cb(request, "", 0)
            except Exception:
                pass
