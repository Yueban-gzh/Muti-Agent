"""
下载 Qwen2.5-3B-Instruct 到项目 models 目录
-------------------------------------------
用法:
    cd backend
    python scripts/download_model.py

脚本会自动：
  - 使用 HF 国内镜像（hf-mirror.com）
  - 临时关闭 http(s)_proxy（代理会导致 SSL EOF）
  - 关闭 XET 加速（走美国 cas-bridge 易超时）
  - 单线程下载大文件（更稳）

支持断点续传：重复运行会继续下载。
"""

from __future__ import annotations

import os
from pathlib import Path

# 必须在 import huggingface_hub 之前
for _key in (
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
    "ALL_PROXY", "all_proxy",
):
    os.environ.pop(_key, None)

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# 禁用 XET 美国 CDN，改用镜像常规 HTTPS（国内更稳）
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from huggingface_hub import hf_hub_download, snapshot_download

REPO_ID = "Qwen/Qwen2.5-3B-Instruct"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_DIR = PROJECT_ROOT / "models" / "Qwen2.5-3B-Instruct"

# 大权重分片（约 6GB，最容易超时）
WEIGHT_FILES = [
    "model-00001-of-00002.safetensors",
    "model-00002-of-00002.safetensors",
]


def _download_weights_one_by_one() -> None:
    """逐个下载大权重文件，失败可单独重试。"""
    for filename in WEIGHT_FILES:
        dest = LOCAL_DIR / filename
        if dest.exists() and dest.stat().st_size > 100_000_000:
            print(f"  跳过（已存在）: {filename} ({dest.stat().st_size / 1e9:.2f} GB)")
            continue
        print(f"\n>>> 正在下载: {filename} （请耐心等待，支持断点续传）")
        hf_hub_download(
            repo_id=REPO_ID,
            filename=filename,
            local_dir=str(LOCAL_DIR),
        )
        print(f"    完成: {filename}")


def main() -> None:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"HF_ENDPOINT      = {os.environ.get('HF_ENDPOINT')}")
    print(f"HF_HUB_DISABLE_XET = {os.environ.get('HF_HUB_DISABLE_XET')}")
    print("已关闭 http(s)_proxy")
    print(f"目标目录: {LOCAL_DIR}\n")

    # 第 1 步：小文件（config / tokenizer 等）
    print("=== 第 1 步：下载配置文件与小文件 ===")
    snapshot_download(
        repo_id=REPO_ID,
        local_dir=str(LOCAL_DIR),
        max_workers=1,
    )

    # 第 2 步：大权重单独下（更稳）
    print("\n=== 第 2 步：下载模型权重（2 个大文件，约 6GB）===")
    _download_weights_one_by_one()

    total = sum(f.stat().st_size for f in LOCAL_DIR.rglob("*") if f.is_file())
    print(f"\n✅ 全部完成，目录总体积: {total / 1e9:.2f} GB")
    print("下一步: python scripts/test_local_llm.py")


if __name__ == "__main__":
    main()
