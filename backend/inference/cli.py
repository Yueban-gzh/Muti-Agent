"""
推理服务启动 CLI & 远程部署脚本生成。
"""

from __future__ import annotations

import os
import sys
import argparse
import textwrap


def build_start_script(model_path: str, host: str = "0.0.0.0", port: int = 30000) -> str:
    """生成远程服务器启动脚本。"""
    return textwrap.dedent(f"""\
    #!/bin/bash
    # Jixia Inference Server — 自研推理引擎启动脚本
    # 自动生成，请勿手动修改

    set -e

    # ── 环境 ──
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    source /root/miniconda3/bin/activate bnn
    export CUDA_VISIBLE_DEVICES=0

    # ── 模型路径 ──
    MODEL_PATH="{model_path}"

    # ── 启动 ──
    echo "[jixia] Starting inference server..."
    echo "[jixia] Model: $MODEL_PATH"
    echo "[jixia] Endpoint: http://{host}:{port}/v1/chat/completions"

    nohup python -m backend.inference.cli \\
        --model-path "$MODEL_PATH" \\
        --host {host} \\
        --port {port} \\
        --max-batch-size 32 \\
        --compile \\
        --warmup \\
        > /ai/data/lyr/sglang/server_jixia.log 2>&1 &

    PID=$!
    echo "[jixia] Server PID: $PID"
    echo $PID > /ai/data/lyr/sglang/jixia_server.pid

    # 等待启动
    echo "[jixia] Waiting for server to start..."
    for i in $(seq 1 30); do
        if curl -s http://{host}:{port}/health > /dev/null 2>&1; then
            echo "[jixia] Server ready! http://{host}:{port}/v1/chat/completions"
            exit 0
        fi
        sleep 2
    done
    echo "[jixia] WARNING: Server may still be loading (model + warmup takes ~30s)"
    echo "[jixia] Check logs: tail -f /ai/data/lyr/sglang/server_jixia.log"
    """)


def main():
    parser = argparse.ArgumentParser(
        description="Jixia Inference Server — 自研推理引擎",
    )
    parser.add_argument("--model-path", default="/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=30000)
    parser.add_argument("--max-batch-size", type=int, default=32)
    parser.add_argument("--max-seq-len", type=int, default=4096)
    parser.add_argument("--kv-cache-total-tokens", type=int, default=32768)
    parser.add_argument("--no-compile", dest="compile", action="store_false", default=True)
    parser.add_argument("--no-warmup", dest="warmup", action="store_false", default=True)
    parser.add_argument("--cuda-graph", action="store_true", default=False)
    parser.add_argument("--no-prefix-cache", dest="prefix_cache", action="store_false", default=True)
    parser.add_argument("--gen-startup-script", action="store_true",
                        help="生成远程启动脚本（不启动服务）")

    args = parser.parse_args()

    if args.gen_startup_script:
        script = build_start_script(args.model_path, args.host, args.port)
        print(script)
        return

    # 导入并启动服务
    from backend.inference.config import ServerConfig, EngineConfig
    from backend.inference.server import run_server

    run_server(
        host=args.host,
        port=args.port,
        model_path=args.model_path,
        max_batch_size=args.max_batch_size,
        max_seq_len=args.max_seq_len,
        kv_cache_total_tokens=args.kv_cache_total_tokens,
        use_torch_compile=args.compile,
        use_cuda_graph=args.cuda_graph,
        use_prefix_cache=args.prefix_cache,
        warmup=args.warmup,
    )


if __name__ == "__main__":
    main()
