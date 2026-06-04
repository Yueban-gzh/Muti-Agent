"""
从 ModelScope（国内）下载 Qwen2.5-3B-Instruct
-------------------------------------------
当 hf-mirror + curl 反复超时时使用。

用法:
    cd backend
    python scripts/download_weights_modelscope.py

下载完成后若路径与 HF 版不同，在 os.env 里设置 LOCAL_MODEL_PATH 指向实际目录。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

for _key in (
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
    "ALL_PROXY", "all_proxy",
):
    os.environ.pop(_key, None)

from modelscope import snapshot_download

REPO_ID = "qwen/Qwen2.5-3B-Instruct"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET = PROJECT_ROOT / "models" / "Qwen2.5-3B-Instruct"


def main() -> None:
    print(f"ModelScope 下载: {REPO_ID}")
    print(f"目标目录: {TARGET}\n")

    # 下载到临时目录再合并（避免与半拉 hf 文件混淆时可删旧 safetensors）
    cache_dir = PROJECT_ROOT / "models" / "_modelscope_cache"
    raw_path = snapshot_download(
        REPO_ID,
        cache_dir=str(cache_dir),
        revision="master",
    )
    src = Path(raw_path)
    TARGET.mkdir(parents=True, exist_ok=True)

    print(f"\n复制文件: {src} -> {TARGET}")
    for item in src.iterdir():
        dest = TARGET / item.name
        if item.is_file():
            shutil.copy2(item, dest)
            print(f"  {item.name}")

    total = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file())
    print(f"\n✅ 完成，目录体积: {total / 1e9:.2f} GB")
    print("下一步: python scripts/test_local_llm.py")


if __name__ == "__main__":
    main()
