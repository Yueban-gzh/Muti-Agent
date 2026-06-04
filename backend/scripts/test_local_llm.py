"""
本地 Qwen 模型 smoke test
-------------------------
用法（在 backend 目录下）:
    python scripts/test_local_llm.py

成功标准: 终端打印一段中文回复，且 cuda: True
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# 模型路径：优先读环境变量，否则用项目默认路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "Qwen2.5-3B-Instruct"


def main() -> None:
    model_path = Path(os.environ.get("LOCAL_MODEL_PATH", str(DEFAULT_MODEL_PATH)))
    if not model_path.exists():
        print(f"❌ 模型目录不存在: {model_path}")
        print("请先完成模型下载，见 docs/本地模型下载.md 或按下面命令:")
        print(
            "  export HF_ENDPOINT=https://hf-mirror.com\n"
            "  hf download Qwen/Qwen2.5-3B-Instruct "
            f"--local-dir {DEFAULT_MODEL_PATH}"
        )
        sys.exit(1)

    print(f"cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    print(f"正在加载模型: {model_path} （首次加载约 1~3 分钟）...")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    messages = [
        {"role": "system", "content": "你是决策分析专家，请用简洁中文回答。"},
        {
            "role": "user",
            "content": "我们团队是否应该开发校园二手交易小程序？请用三句话说明理由。",
        },
    ]

    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    print("正在生成...")
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
        )

    new_tokens = output_ids[0][inputs["input_ids"].shape[1] :]
    reply = tokenizer.decode(new_tokens, skip_special_tokens=True)

    print("\n" + "=" * 50)
    print("模型回复:")
    print("=" * 50)
    print(reply)
    print("=" * 50)
    print("✅ 本地模型测试通过")


if __name__ == "__main__":
    main()
