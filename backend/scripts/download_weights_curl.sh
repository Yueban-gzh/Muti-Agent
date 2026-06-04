#!/usr/bin/env bash
# curl/wget 断点续传下载权重 — 失败可反复执行，每次接着下
set -euo pipefail

BASE="https://hf-mirror.com/Qwen/Qwen2.5-3B-Instruct/resolve/main"
DIR="/ai/data/lyr/muti-agent/models/Qwen2.5-3B-Instruct"
mkdir -p "$DIR"

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy

download_one() {
  local file="$1"
  local url="${BASE}/${file}"
  local out="${DIR}/${file}"
  echo ""
  echo ">>> ${file}"
  if [[ -f "$out" ]]; then
    echo "    已有: $(du -h "$out" | cut -f1)"
  fi

  # 优先 wget（断点续传 + 无限重试）
  if command -v wget >/dev/null 2>&1; then
    wget -c --timeout=30 --tries=0 --read-timeout=60 \
      -O "${out}" "${url}" || true
  else
    curl -L -C - --connect-timeout 30 \
      --retry 999 --retry-all-errors --retry-delay 10 \
      -o "${out}" "${url}" || true
  fi

  if [[ -f "$out" ]]; then
    ls -lh "${out}"
  fi
}

# 期望大小（字节，约值）：00001≈3.97GB，00002≈2.20GB
check_size() {
  local file="$1" min_bytes="$2"
  local out="${DIR}/${file}"
  if [[ ! -f "$out" ]]; then return 1; fi
  local sz
  sz=$(stat -c%s "$out" 2>/dev/null || stat -f%z "$out")
  [[ "$sz" -ge "$min_bytes" ]]
}

download_one "model-00001-of-00002.safetensors"
download_one "model-00002-of-00002.safetensors"

echo ""
du -sh "$DIR"

if check_size "model-00001-of-00002.safetensors" 3900000000 \
   && check_size "model-00002-of-00002.safetensors" 2100000000; then
  echo "✅ 两个权重文件大小正常。下一步: python scripts/test_local_llm.py"
else
  echo "⚠️  文件未下完整，请再次运行本脚本续传，或改用:"
  echo "    python scripts/download_weights_modelscope.py"
  exit 1
fi
