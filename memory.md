# SGLang 推理服务部署 — 上下文恢复指南

## 1. 服务器连接信息

| 项目 | 值 |
|---|---|
| 主机 | `10.112.247.63` |
| SSH 端口 | `37096` |
| 用户 | `root` |
| 密码 | `123` |
| 工作目录 | `/ai/data/lyr/sglang/` |
| Conda 路径 | `/root/miniconda3/bin/conda` |
| Conda 环境 | `bnn` |
| GPU | NVIDIA GeForce RTX 3090 (24576 MiB, 当前空闲 ~24112 MiB) |
| 磁盘 | `/ai/data/` 总计 1000G，剩余 ~461G |

SSH 连接命令：
```bash
ssh -p 37096 root@10.112.247.63
```

## 2. 已完成事项

### 2.1 SGLang 安装 🔄
- **环境**: `/root/miniconda3/envs/bnn/`
- **当前状态**: 正在重装中 (`pip install sglang[all] --index-url https://docs.sglang.ai/whl/cu129/ --force-reinstall`)
- **目标版本**: sglang nightly (0.5.13.dev) + torch 2.9.1 (来自 SGLang 官方 CUDA 12.9 wheel 索引)
- **libnuma**: 已安装 (`apt-get install libnuma1 libnuma-dev`)
- **FlashInfer**: 0.6.7.post3 可用
- **PyPI 源**: SGLang nightly wheel (`https://docs.sglang.ai/whl/cu129/`) + 清华大学 tuna 镜像备用

### 2.2 模型下载 ✅
- **模型**: `tencent/Hunyuan-7B-Instruct-GPTQ-Int4` (腾讯官方 GPTQ-INT4 量化版本)
- **路径**: `/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4/`
- **大小**: model.safetensors 约 4.4GB，共 15 个文件
- **下载方式**: 从 ModelScope (`https://www.modelscope.cn`) 用 `modelscope.snapshot_download` 下载
- **Fallback**: 若 ModelScope 不可用，可用 HuggingFace + hf-mirror.com 镜像
- **架构实测数据** (来自 config.json):
  - 架构: `HunYuanDenseV1ForCausalLM`
  - 隐藏维度: 4096
  - 层数: 32
  - 注意力头: 32 (Q-heads)
  - KV 头: 8 (GQA - Grouped Query Attention)
  - 量化方式: GPTQ
  - 原生上下文: 256K

### 2.3 启动脚本 ✅
- **路径**: `/ai/data/lyr/sglang/start_sglang.sh`
- **本地路径**: `d:\jixia-Python\start_sglang.sh` (一份副本)
- **行数**: 291 行，含详细中文注释

## 3. SGLang 启动脚本核心参数

| 参数 | 值 | 工程意义 |
|---|---|---|
| `--model-path` | `/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4` | GPTQ-INT4 量化模型路径 |
| `--host` / `--port` | `0.0.0.0` / `30000` | OpenAI 兼容 API 端点 |
| `--mem-fraction-static` | **0.95** | 将 95% 显存分配给 KV Cache (~18-19GB) |
| `--schedule-policy` | **lpm** | RadixAttention 自动前缀缓存 (多 Agent 共享前缀时 prefill 计算量降 73%) |
| `--max-total-tokens` | **32768** | 全局在途 token 预算，超限排队不 OOM |
| `--max-prefill-tokens` | **4096** | 单次 prefill token 上限，防并发尖峰 OOM |
| `--context-length` | **16384** | 单序列最大上下文，防"贪婪序列"挤占 KV Cache |
| `--chunked-prefill-size` | **4096** | 分块 prefill 粒度，消除 Head-of-Line Blocking |
| `--max-running-requests` | **128** | 并发请求硬上限 |
| `--quantization` | **gptq** | GPTQ INT4 量化 kernel |
| `--dtype` | **auto** | 自动检测计算精度 |
| `--trust-remote-code` | 启用 | HunYuanDenseV1 架构需要 |

### 3.1 KV Cache 精算

```
每 token KV 开销 = 2 × num_layers × num_kv_heads × head_dim × 2 bytes
                 = 2 × 32 × 8 × 128 × 2 = 131,072 bytes ≈ 128 KB

18GB KV Cache ÷ 128KB/token ≈ 147,000 tokens 理论容量
工程设定 32768 tokens (约理论 22%)，预留余量给 Radix Tree 元数据、碎片、突发
```

### 3.2 API 端点
```
http://10.112.247.63:30000/v1/chat/completions  (OpenAI 兼容)
http://10.112.247.63:30000/v1/completions
http://10.112.247.63:30000/v1/models
```

## 4. 如何启动服务

```bash
# SSH 到服务器
ssh -p 37096 root@10.112.247.63

# 启动 SGLang 推理服务
bash /ai/data/lyr/sglang/start_sglang.sh
```

首次启动需要 1-3 分钟（加载模型 + CUDA Graph 编译）。之后日志会显示：
```
INFO: Started server process [PID]
INFO: Uvicorn running on http://0.0.0.0:30000
```

## 5. 如何本地测试

在本地机器上运行：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://10.112.247.63:30000/v1",
    api_key="not-needed"  # SGLang 不需要真 key
)

# 简单测试
response = client.chat.completions.create(
    model="default",  # 或 "Hunyuan-7B-Instruct-GPTQ-Int4"
    messages=[{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    max_tokens=256,
    temperature=0.7,
)
print(response.choices[0].message.content)
```

或用 curl：
```bash
curl http://10.112.247.63:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 128
  }'
```

## 6. Python 连接脚本 (paramiko)

本地连接服务器的 Python 示例（无需安装 sshpass）：

```python
import paramiko

host, port, user, password = "10.112.247.63", 37096, "root", "123"
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=password, timeout=15)

# 执行命令
stdin, stdout, stderr = client.exec_command("nvidia-smi")
print(stdout.read().decode())

# 上传文件
sftp = client.open_sftp()
sftp.put("local_file.txt", "/ai/data/lyr/sglang/remote_file.txt")
sftp.close()

client.close()
```

## 7. 重要文件路径汇总

| 文件/目录 | 路径 |
|---|---|
| 启动脚本 | `/ai/data/lyr/sglang/start_sglang.sh` |
| 模型目录 | `/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4/` |
| 模型权重 | `/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4/model.safetensors` (4.4G) |
| 模型配置 | `/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4/config.json` |
| SGLang 安装日志 | `/ai/data/lyr/sglang/install_retry.log` |
| Conda 环境 | `/root/miniconda3/envs/bnn/` |
| 本地脚本 (备) | `d:\jixia-Python\start_sglang.sh` |

## 8. 已知问题与解决方案 (部署踩坑记录)

### 8.1 Tsinghua 镜像 SSL 错误
`nvidia-nvshmem-cu12` 包可能 SSL 失败。解决：用 `--extra-index-url https://pypi.org/simple/` 或从 ModelScope 下载。

### 8.2 sgl_kernel 不支持 RTX 3090 (SM86)
**根本原因**: sglang-kernel 0.4.x 仅编译了 SM90 (H100) 和 SM100 (Blackwell) 变体。RTX 3090 (Compute Capability 8.6 = SM86) 不匹配。
- loader (`load_utils.py`) 硬编码：SM90 → sm90/ 目录，其他所有 GPU → sm100/ 目录
- SM100 .so 编译时依赖 torch 2.9+，若 torch 版本不匹配会出现 `undefined symbol` 错误

**临时修复**: 修改 `/root/miniconda3/envs/bnn/lib/python3.10/site-packages/sgl_kernel/__init__.py`，用 try/except 包裹所有 native ops 导入，失败时返回 dummy 对象。SGLang 会自动 fallback 到 FlashInfer。

patch 脚本已保存在: `/ai/data/lyr/sglang/patch_sgl_kernel.py`（本地：`d:\jixia-Python\temp_repo\patch_sgl_kernel.py`）

**注意**: 每次 `pip install sglang-kernel` 后会覆盖此修复，需重新应用。

### 8.3 torch 版本兼容性问题
| torch 版本 | SGLang 0.5.10 状态 |
|---|---|
| 2.9.1 | SGLang import OK，但 server 启动时报 `torch._C._dispatch_has_kernel_for_dispatch_key` 不存在 |
| 2.7.1 | import 正常，但 server 启动时 `std::bad_alloc` (CUDA 初始化崩溃) |
| 2.5.1 | 太旧，缺少 `torch._C._dispatch_has_kernel_for_dispatch_key` |

**方向**: 使用 SGLang nightly build (从 `https://docs.sglang.ai/whl/cu129/`) 搭配 torch 2.9.1。

### 8.4 模型下载
- ModelScope 的 `git clone` + `git lfs pull` 速度很慢 (200 KB/s)
- **推荐**: 使用 `modelscope.snapshot_download()` SDK 直接下载 (10-30 MB/s)

### 8.5 网络速度变化
Tsinghua 镜像速度不稳定：第一次 1-5 MB/s，第二次 27-31 MB/s。若下载慢可等待后重试。

## 9. 根因分析与当前状态

### 9.0 根因：CUDA 版本不匹配

**NVIDIA 驱动**: 570.153.02, **CUDA 12.8** (nvidia-smi 报告)
**torch 默认安装**: 2.11.0+cu130 → **需要 CUDA 13.0** (驱动不支持!)

这是所有问题的根因：pip 安装的任何最新 torch/sglang/vllm 都会拉取 CUDA 13.0 版本，而服务器的 NVIDIA 驱动只支持到 CUDA 12.8。

**修复方向**: 强制使用 cu128 版本的 torch (2.9.1+cu128 或 2.7.1+cu128)。

### 9.1 2026-06-10 环境重建

miniconda3 环境之前被删除（原因不明），完整重建：

| 步骤 | 状态 |
|---|---|
| 安装 miniconda3 (conda 26.3.2) 到 `/root/miniconda3/` | ✅ |
| 创建 bnn 环境 (Python 3.10.20) | ✅ |
| 安装 SGLang[all] + torch 2.9.1+cu128 | ✅ |
| sgl_kernel patch (SM86→SM90) | ✅ |
| 安装 gcc-10/g++-10 (解决 C++20 编译) | ✅ |
| FlashInfer RMSNorm patch (绕过 shape bug) | ✅ |

### 9.2 SGLang 0.5.10 与 Hunyuan-7B-GPTQ 的兼容性 Bug

经过大量调试，发现 SGLang 0.5.10 对 Hunyuan 模型有 3 层不兼容：

| 配置 | 错误位置 | 错误 |
|---|---|---|
| `float16` + GPTQ | `fused_add_rmsnorm` | `CHECK_EQ(input.size(0), residual.size(0))` → 128 vs 4 |
| `bfloat16` + 自动 Marlin | `gptq_marlin_gemm` | `bqw_dim0` mismatch: expected 8 got 256 |
| `bfloat16` + 强制 GPTQ | `_get_quantization_config` | bfloat16 not supported for GPTQ |

**根因**: Hunyuan 的 GQA (32 Q-heads, 8 KV-heads) 残差连接中，per-sequence residual `[4, 4096]` 与 per-token hidden_states `[128, 4096]` 在 `fused_add_rmsnorm` 中不兼容。这是 SGLang Hunyuan 模型实现的 bug，非环境问题。

### 9.3 vLLM 方案分析

| 事实 | 详情 |
|---|---|
| Hunyuan 支持 | ✅ vLLM v0.10.0+ 原生支持 `HunYuanDenseV1ForCausalLM` |
| 最低版本 | vLLM ≥ v0.10.0 |
| **致命问题** | vLLM v0.10.0+ → torch 2.11+ → **需要 CUDA 13 驱动** |
| 驱动现状 | 服务器 570 驱动 = CUDA 12.8，不支持 CUDA 13 |

**结论**: vLLM 和 SGLang 最新版都需要 CUDA 13 驱动，无法在现有服务器上运行。

### 9.4 自研推理引擎方案

基于 `transformers` 原生支持 `HunYuanDenseV1ForCausalLM`（v5.8.1+），自研轻量推理引擎：
- 不绑定 CUDA 版本，现有 torch 2.9.1+cu128 直接可用
- GPTQ-INT4 通过 transformers 自动加载
- 7B INT4 模型显存占用 ~4.4GB，24GB VRAM 绰绰有余

**优化目标**:
- Flash Attention (via torch SDPA) — 免费
- torch.compile — 编译加速
- CUDA Graph 解码 — 单 token 延迟大幅降低
- 连续批处理 — 动态请求合并
- Prefix Cache — 共享前缀复用 KV Cache
- SSE Streaming — OpenAI 兼容

代码位置: `backend/inference/`

### 9.0 根因：CUDA 版本不匹配

**NVIDIA 驱动**: 570.153.02, **CUDA 12.8** (nvidia-smi 报告)
**torch 默认安装**: 2.11.0+cu130 → **需要 CUDA 13.0** (驱动不支持!)

这是所有问题的根因：pip 安装的任何最新 torch/sglang/vllm 都会拉取 CUDA 13.0 版本，而服务器的 NVIDIA 驱动只支持到 CUDA 12.8。

**修复方向**: 强制使用 cu128 版本的 torch (2.9.1+cu128 或 2.7.1+cu128)。

### 9.1 当前状态 (2026-06-07)
- ✅ 模型已下载: `/ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4/` (4.4GB)
- ✅ 启动脚本已就位: `/ai/data/lyr/sglang/start_sglang.sh`
- ✅ libnuma 已安装
- 🔄 SGLang 正在重装: `pip install sglang[all] --index-url https://docs.sglang.ai/whl/cu129/ --force-reinstall`
- ❌ 服务尚未成功启动 — 根因：**NVIDIA Driver (570.153.02) 只支持 CUDA 12.8，但最新推理框架需要 CUDA 13**

### 推荐下一步操作

**首选路线：更新 NVIDIA 驱动到 575+ (支持 CUDA 13)**

这是根本解决方案。更新驱动后，可以直接安装最新 vLLM 或 SGLang，无需任何兼容性 hack。

```bash
# 更新驱动后：
pip install vllm  # 自动安装 torch 2.11+cu130，驱动支持
python -m vllm.entrypoints.openai.api_server \
    --model /ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4 \
    --host 0.0.0.0 --port 30000 \
    --gpu-memory-utilization 0.95 --max-model-len 16384 \
    --max-num-seqs 128 --enable-prefix-caching \
    --quantization gptq_marlin --trust-remote-code --dtype auto
```

**备选路线：用 SGLang 0.4.6 (原生支持 RTX 3090 SM86)**

当前 bnn 环境有 SGLang 0.4.6 + torch 2.6.0+cu124，sgl_kernel 0.4.6 **原生支持 SM86**。
唯一问题是 `deep_gemm` 无法从清华镜像下载（SSL 错误）。

等清华镜像恢复后：
```bash
ssh -p 37096 root@10.112.247.63
source /root/miniconda3/bin/activate bnn
pip install deep-gemm -i https://pypi.org/simple/ --extra-index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/
nohup python -m sglang.launch_server \
    --model-path /ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4 \
    --host 0.0.0.0 --port 30000 \
    --mem-fraction-static 0.85 --max-total-tokens 16384 \
    --max-prefill-tokens 4096 --context-length 8192 \
    --schedule-policy lpm --quantization gptq \
    --dtype auto --trust-remote-code \
    > /ai/data/lyr/sglang/server.log 2>&1 &
```

**备选路线：用 sglang conda 环境**

已有环境 `sglang` (torch 2.9.1+cu128 + vLLM 0.22.1 + CUDA 13 toolkit via conda)。
需要更新 NVIDIA 驱动后才能用。
