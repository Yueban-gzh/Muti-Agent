"""
OpenAI 兼容 API 服务。

端点:
  POST /v1/chat/completions  — Chat Completions (SSE streaming)
  POST /v1/completions        — Text Completions
  GET  /v1/models             — 模型列表
  GET  /health                — 健康检查

架构:
  FastAPI (async) ←→ InferenceEngine (后台线程，连续批处理)
                       ↑
                  asyncio.Queue 桥接

流式输出使用 Server-Sent Events (SSE):
  data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}\n\n
  data: [DONE]\n\n
"""

from __future__ import annotations

import json
import time
import uuid
import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.inference.config import ServerConfig, EngineConfig
from backend.inference.engine import InferenceEngine, GenerationRequest

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# OpenAI 兼容 Pydantic Models
# ═══════════════════════════════════════════


class Message(BaseModel):
    role: str = "user"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: List[Message]
    max_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int = Field(default=50, ge=1, le=100)
    stream: bool = False
    stop: Optional[List[str]] = None


class CompletionRequest(BaseModel):
    model: str = "default"
    prompt: str
    max_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    stream: bool = False
    stop: Optional[List[str]] = None


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "jixia"


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


# ═══════════════════════════════════════════
# 引擎管理器 (全局单例)
# ═══════════════════════════════════════════


class EngineManager:
    """管理引擎生命周期，提供 async 接口。"""

    def __init__(self, server_config: ServerConfig, engine_config: EngineConfig):
        self.server_config = server_config
        self.engine_config = engine_config
        self._engine: Optional[InferenceEngine] = None
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return

        logger.info("Initializing inference engine...")
        self._engine = InferenceEngine(self.engine_config)
        self._engine.initialize()
        self._engine.start()
        self._initialized = True
        logger.info("Inference engine ready")

    def shutdown(self):
        if self._engine:
            self._engine.stop()
        self._initialized = False

    @property
    def engine(self) -> InferenceEngine:
        if not self._engine:
            raise RuntimeError("Engine not initialized")
        return self._engine

    @property
    def model_name(self) -> str:
        return self.server_config.model_name

    def build_prompt_from_messages(self, messages: List[Message]) -> str:
        """Hunyuan chat template 构建 prompt。"""
        # Hunyuan-7B 使用 jinja2 chat template
        engine = self.engine
        if hasattr(engine.tokenizer, "apply_chat_template"):
            msgs = [{"role": m.role, "content": m.content} for m in messages]
            return engine.tokenizer.apply_chat_template(
                msgs,
                tokenize=False,
                add_generation_prompt=True,
            )
        # Fallback: 简单拼接
        parts = []
        for m in messages:
            if m.role == "system":
                parts.append(f"<|system|>\n{m.content}</s>")
            elif m.role == "user":
                parts.append(f"<|user|>\n{m.content}</s>")
            elif m.role == "assistant":
                parts.append(f"<|assistant|>\n{m.content}</s>")
        parts.append("<|assistant|>\n")
        return "\n".join(parts)


# 全局管理器实例（由 create_app 设置）
_manager: Optional[EngineManager] = None


def get_manager() -> EngineManager:
    assert _manager is not None, "Engine not initialized"
    return _manager


# ═══════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化引擎，关闭时清理。"""
    global _manager
    logger.info("Starting inference server...")
    _manager.initialize()
    yield
    logger.info("Shutting down inference server...")
    _manager.shutdown()


def create_app(
    server_config: Optional[ServerConfig] = None,
    engine_config: Optional[EngineConfig] = None,
) -> FastAPI:
    """创建 FastAPI 应用。"""
    global _manager

    if server_config is None:
        server_config = ServerConfig()
    if engine_config is None:
        engine_config = EngineConfig()

    _manager = EngineManager(server_config, engine_config)

    # 配置日志
    logging.basicConfig(
        level=getattr(logging, server_config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = FastAPI(
        title="Jixia Inference API",
        version="1.0.0",
        description="OpenAI-compatible inference server for Hunyuan-7B GPTQ-INT4",
        lifespan=lifespan,
    )

    # CORS — 允许任何来源（本地 HTML 通过 file:// 访问时需要）
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ──── 健康检查 ────

    @app.get("/health")
    async def health():
        engine = _manager.engine if _manager._initialized else None
        return {
            "status": "ok" if engine else "initializing",
            "model": _manager.model_name,
            "initialized": _manager._initialized,
        }

    # ──── 模型列表 ────

    @app.get("/v1/models")
    async def list_models():
        return ModelsResponse(
            data=[
                ModelInfo(
                    id=_manager.model_name,
                    created=int(time.time()),
                    owned_by="jixia",
                )
            ]
        )

    # ──── Chat Completions ────

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
        """OpenAI 兼容 Chat Completions 端点。"""
        manager = get_manager()
        engine = manager.engine

        # 构建 prompt
        prompt = manager.build_prompt_from_messages(request.messages)

        # 创建请求
        req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        gen_req = GenerationRequest(
            request_id=req_id,
            prompt=prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            stop_sequences=request.stop or [],
        )

        if request.stream:
            return StreamingResponse(
                _stream_chat_completion(engine, gen_req, req_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            return await _sync_chat_completion(engine, gen_req, req_id)

    # ──── Completions ────

    @app.post("/v1/completions")
    async def completions(request: CompletionRequest, raw_request: Request):
        """OpenAI 兼容 Text Completions 端点。"""
        manager = get_manager()
        engine = manager.engine

        req_id = f"cmpl-{uuid.uuid4().hex[:12]}"
        gen_req = GenerationRequest(
            request_id=req_id,
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            stop_sequences=request.stop or [],
        )

        if request.stream:
            return StreamingResponse(
                _stream_completion(engine, gen_req, req_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            return await _sync_completion(engine, gen_req, req_id)

    return app


# ═══════════════════════════════════════════
# 流式输出 (SSE)
# ═══════════════════════════════════════════


async def _stream_chat_completion(
    engine: InferenceEngine,
    request: GenerationRequest,
    req_id: str,
) -> AsyncGenerator[str, None]:
    """Chat Completions SSE 流式输出。"""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_token(req: GenerationRequest, token_text: str, token_id: int):
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {
                "text": token_text,
                "token_id": token_id,
                "finish_reason": req.finish_reason if req.finished else None,
            },
        )

    engine.submit(request, on_token)
    created = int(time.time())

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=60)
        except asyncio.TimeoutError:
            break

        finish_reason = event.get("finish_reason")
        chunk = {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "default",
            "choices": [{
                "index": 0,
                "delta": {"content": event["text"]} if not finish_reason else {},
                "finish_reason": finish_reason,
            }],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        if finish_reason:
            yield "data: [DONE]\n\n"
            break


async def _stream_completion(
    engine: InferenceEngine,
    request: GenerationRequest,
    req_id: str,
) -> AsyncGenerator[str, None]:
    """Text Completions SSE 流式输出。"""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_token(req: GenerationRequest, token_text: str, token_id: int):
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {
                "text": token_text,
                "finish_reason": req.finish_reason if req.finished else None,
            },
        )

    engine.submit(request, on_token)
    created = int(time.time())

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=60)
        except asyncio.TimeoutError:
            break

        finish_reason = event.get("finish_reason")
        chunk = {
            "id": req_id,
            "object": "text_completion.chunk",
            "created": created,
            "model": "default",
            "choices": [{
                "index": 0,
                "text": event["text"],
                "finish_reason": finish_reason,
            }],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        if finish_reason:
            yield "data: [DONE]\n\n"
            break


# ═══════════════════════════════════════════
# 同步输出 (非流式)
# ═══════════════════════════════════════════


def _build_chat_response(req_id: str, all_text: str, request: GenerationRequest, finish_reason: str) -> dict:
    return {
        "id": req_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "default",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": all_text},
            "finish_reason": finish_reason,
        }],
        "usage": {
            "prompt_tokens": len(request.token_ids),
            "completion_tokens": len(request.generated_ids),
            "total_tokens": len(request.token_ids) + len(request.generated_ids),
        },
    }


async def _sync_chat_completion(
    engine: InferenceEngine,
    request: GenerationRequest,
    req_id: str,
) -> JSONResponse:
    """非流式 Chat Completion。"""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    all_text = ""
    finish_reason = "length"  # default

    def on_token(req: GenerationRequest, token_text: str, token_id: int):
        nonlocal all_text, finish_reason
        all_text += token_text
        if req.finished:
            finish_reason = req.finish_reason
            loop.call_soon_threadsafe(queue.put_nowait, True)

    engine.submit(request, on_token)

    try:
        await asyncio.wait_for(queue.get(), timeout=120)
    except asyncio.TimeoutError:
        pass

    return JSONResponse(content=_build_chat_response(req_id, all_text, request, finish_reason))


async def _sync_completion(
    engine: InferenceEngine,
    request: GenerationRequest,
    req_id: str,
) -> JSONResponse:
    """非流式 Text Completion。"""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    all_text = ""
    finish_reason = "length"

    def on_token(req: GenerationRequest, token_text: str, token_id: int):
        nonlocal all_text, finish_reason
        all_text += token_text
        if req.finished:
            finish_reason = req.finish_reason
            loop.call_soon_threadsafe(queue.put_nowait, True)

    engine.submit(request, on_token)

    try:
        await asyncio.wait_for(queue.get(), timeout=120)
    except asyncio.TimeoutError:
        pass

    return JSONResponse(content={
        "id": req_id,
        "object": "text_completion",
        "created": int(time.time()),
        "model": "default",
        "choices": [{"index": 0, "text": all_text, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": len(request.token_ids),
            "completion_tokens": len(request.generated_ids),
            "total_tokens": len(request.token_ids) + len(request.generated_ids),
        },
    })


# ═══════════════════════════════════════════
# 入口点
# ═══════════════════════════════════════════


def run_server(
    host: str = "0.0.0.0",
    port: int = 30000,
    model_path: str = "/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4",
    **kwargs,
):
    """启动推理服务。"""
    # 已知的 engine 参数（不在 ServerConfig 中的）
    engine_keys = {
        "max_seq_len", "kv_cache_total_tokens", "use_torch_compile",
        "torch_compile_mode", "use_cuda_graph", "cuda_graph_max_batch_size",
        "use_prefix_cache", "prefix_cache_max_entries", "warmup",
        "max_model_len", "dtype", "device", "batch_timeout_ms",
    }
    engine_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in engine_keys}

    server_config = ServerConfig(
        host=host,
        port=port,
        model_path=model_path,
        model_name=kwargs.pop("model_name", "Hunyuan-7B-Instruct-GPTQ-Int4"),
        max_batch_size=kwargs.pop("max_batch_size", 32),
        **kwargs,
    )
    engine_config = EngineConfig(
        model_path=model_path,
        max_batch_size=server_config.max_batch_size,
        **engine_kwargs,
    )

    app = create_app(server_config, engine_config)
    uvicorn.run(app, host=host, port=port, log_level=server_config.log_level)
