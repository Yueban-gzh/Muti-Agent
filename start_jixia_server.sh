#!/bin/bash
# ==============================================
# Jixia Inference Server — 自研推理引擎启动脚本
# 模型: Hunyuan-7B-Instruct-GPTQ-Int4
# GPU:  RTX 3090 (24GB)
# ==============================================
set -e

# ── 环境配置 ──
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
export CUDA_VISIBLE_DEVICES=0

# Conda 环境
source /root/miniconda3/bin/activate bnn

# 模型路径
MODEL_PATH="/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4"
HOST="0.0.0.0"
PORT=30000

# 日志
LOG_DIR="/ai/data/lyr/sglang"
LOG_FILE="$LOG_DIR/server_jixia.log"
PID_FILE="$LOG_DIR/jixia_server.pid"

echo "=============================================="
echo " Jixia Inference Server"
echo " Model:  Hunyuan-7B-Instruct-GPTQ-Int4"
echo " GPU:    RTX 3090 (24GB)"
echo " API:    http://${HOST}:${PORT}/v1/chat/completions"
echo "=============================================="

# 杀掉旧进程
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[jixia] Stopping old server (PID $OLD_PID)..."
        kill "$OLD_PID"
        sleep 2
    fi
fi

# 启动
echo "[jixia] Starting server..."
nohup python -m backend.inference.cli \
    --model-path "$MODEL_PATH" \
    --host "$HOST" \
    --port "$PORT" \
    --max-batch-size 8 \
    --max-seq-len 4096 \
    --kv-cache-total-tokens 32768 \
    --compile \
    --warmup \
    > "$LOG_FILE" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"
echo "[jixia] Server PID: $SERVER_PID"

# 等待启动 (模型加载 + warmup 约 30 秒)
echo "[jixia] Waiting for server to be ready..."
for i in $(seq 1 60); do
    if curl -s "http://${HOST}:${PORT}/health" > /dev/null 2>&1; then
        echo ""
        echo "=============================================="
        echo " Server Ready!"
        echo " API:  http://${HOST}:${PORT}/v1/chat/completions"
        echo " Docs: http://${HOST}:${PORT}/docs"
        echo " Logs: tail -f $LOG_FILE"
        echo "=============================================="
        exit 0
    fi
    printf "."
    sleep 2
done

echo ""
echo "[jixia] WARNING: Server may still be initializing."
echo "[jixia] Check: tail -f $LOG_FILE"
