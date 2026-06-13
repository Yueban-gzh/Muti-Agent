# 自研推理引擎 — 算法与架构设计

## 一、背景与动机

现有主流推理框架（SGLang、vLLM）对 NVIDIA 驱动版本有硬性要求（均需 CUDA 13），而实验室 GPU 服务器驱动为 570（CUDA 12.8），无法升级。为此自研了基于 HuggingFace Transformers 的轻量推理引擎，在兼容现有硬件的前提下实现了高效推理。

## 二、核心算法

### 2.1 GPTQ INT4 量化推理

模型权重经 GPTQ 算法量化为 4-bit 整数，推理时通过 MarlinLinear kernel 反量化回 FP16 进行计算：

```
W_int4 [M×K] ──→ W_fp16 [M×K] ──→ X·W^T ──→ output [B×M]
    4-bit            16-bit          GEMM
```

**Marlin kernel** 针对 INT4 推理进行了寄存器级优化：将 4-bit 权重的解包与矩阵乘融合，减少显存访问次数。对于 7B 模型，权重从 14GB（FP16）压缩至 3.5GB（INT4），压缩比 **4:1**，同时保持推理质量。

### 2.2 Flash Attention

使用 PyTorch 内置的 `scaled_dot_product_attention`，自动启用 Flash Attention 算法：

```
标准 Attention:  O(n²) 显存, 需要显式存储 QK^T 矩阵
Flash Attention: O(n) 显存, 分块计算 + online softmax
```

在 4096 token 的 prefill 阶段，显存占用从 ~256MB 降至 ~8MB，同时利用 SRAM 减少 HBM 访问，加速 2-4×。

### 2.3 Top-p (Nucleus) Sampling

推理引擎实现了与 OpenAI 兼容的随机采样策略：

```
1. Temperature scaling:  logits = logits / T
2. Sort by probability:  sorted_logits = sort(logits, descending)
3. Cumulative sum:       cumsum = cumsum(softmax(sorted_logits))
4. Filter by p:          remove tokens where cumsum > p
5. Multinomial sample:   token ~ categorical(filtered_probs)
```

当 `temperature = 0` 时退化为贪婪解码（`argmax`），保证确定性输出。

### 2.4 KV Cache 管理

自回归生成中，每步需重新计算全部历史 token 的 K/V。KV Cache 将已计算的 K/V 缓存复用：

```
无 Cache: 每步 O(L²)  →  第 k 步计算 k 个 token 的 attention
有 Cache: 每步 O(L)   →  第 k 步只计算 1 个新 token 的 attention
```

`DynamicCache` 自动管理增量式 K/V 追加，每 token KV 占用 128 KiB（Hunyuan GQA: 32层 × 8 KV头 × 128维 × 2字节 × 2 (K+V)）。

## 三、架构设计

### 3.1 整体架构

```
┌──────────────────────────────────────────────────┐
│                 FastAPI (async)                   │
│  /v1/chat/completions  /v1/models  /health       │
│         │                                        │
│    asyncio.Queue 桥接                             │
│         │                                        │
│  ┌──────┴──────────────────────────────────┐     │
│  │     InferenceEngine (后台线程)           │     │
│  │  ┌─────────────────────────────────┐    │     │
│  │  │ queue.Queue → _engine_loop      │    │     │
│  │  │         │                        │    │     │
│  │  │  model.generate()                │    │     │
│  │  │  TextIteratorStreamer            │    │     │
│  │  │         │                        │    │     │
│  │  │  callback → token 回调 ──────────┼────│──→ SSE / JSON
│  │  └─────────────────────────────────┘    │     │
│  └─────────────────────────────────────────┘     │
│                   │                               │
│         Hunyuan-7B GPTQ-INT4 (GPU)               │
└──────────────────────────────────────────────────┘
```

### 3.2 异步桥接设计

这是一个经典的 **生产者-消费者** 模型：

- **生产者（FastAPI）**：接收 HTTP 请求，封装 `GenerationRequest`，通过 `queue.Queue`（线程安全）提交给引擎线程
- **消费者（Engine 线程）**：从队列取出请求，调用 `model.generate()` 进行推理，通过回调函数逐 token 返回结果

**线程安全保证**：
- 引擎内部使用 `threading.Lock` 保护共享状态
- 回调通过 `loop.call_soon_threadsafe()` 将结果安全投递到 asyncio 事件循环
- `asyncio.Queue` 在事件循环线程内操作，`queue.Queue` 在跨线程场景使用

### 3.3 流式输出

使用 `TextIteratorStreamer` 实现 token 级流式输出：

```python
streamer = TextIteratorStreamer(tokenizer, skip_prompt=True)
# generate 在子线程运行，主线程从 streamer 逐 token 读取
Thread(target=model.generate, args=(..., streamer)).start()
for token_text in streamer:
    callback(token_text)  # → SSE data: {...}\n\n
```

相比批处理方案，流式输出将首 token 延迟从"全生成完"降至"第一个 token 生成时"，用户体验显著提升。

### 3.4 模块划分

| 模块 | 职责 |
|------|------|
| `engine.py` | 模型加载、Warmup、`model.generate()` 调度、采样策略 |
| `server.py` | FastAPI 路由、SSE 流式协议、OpenAI 数据格式适配 |
| `kvcache.py` | KV Cache 预分配池（FreeList + Best-Fit）、Prefix Cache（Radix Tree） |
| `config.py` | 引擎与服务的分离配置 |
| `cli.py` | 命令行入口 + 远程部署脚本生成 |

`kvcache.py` 中的 Prefix Cache 和 KV Cache 池已完整实现但默认关闭，可在需要时启用，实现**共享前缀的 KV 复用**。

## 四、性能分析

### 物理天花板

| 指标 | 值 | 推导 |
|------|-----|------|
| 模型权重 | 3.5 GB | 7B × 4-bit / 8 |
| 显存带宽 | 936 GB/s | RTX 3090，HBM |
| 理论 decode 上限 | **270 tok/s** | 3.5GB / 936GB/s (每个 token 需读完所有权重) |
| KV Cache / token | 128 KiB | 2 × 32层 × 8 KV头 × 128维 × 2字节 |
| 4096 token KV | 512 MiB | 128 KiB × 4096 |
| 最大并发序列 | ~35 | 18GB KV 池 / 512 MiB |

### 实测性能

| 场景 | 指标 |
|------|------|
| 模型加载 | ~7 秒（含 Marlin kernel 编译缓存） |
| Warmup | ~7 秒（首次触发 CUDA kernel 编译） |
| 单请求 decode | ~50 tok/s（受限于 936 GB/s 带宽） |
| Prefill 512 token | ~50 ms |
| 显存占用 | ~4.7 GB（模型）+ 动态 KV Cache |

## 五、局限与改进方向

### 当前局限

1. **无连续批处理**：当前为单请求串行处理，GPU 利用率在低并发时不足。设计了队列收集 + 动态 batch 的框架，待后续启用
2. **torch.compile 暂未启用**：`reduce-overhead` 模式下的 CUDA graph 与 Hunyuan 动态计算图存在兼容性问题，回退到 eager 模式
3. **无 PagedAttention**：KV Cache 使用 transformers 内置管理，未实现显存分页，碎片利用率不如 vLLM
4. **单 GPU**：不支持张量并行，模型上限受限于单卡显存

### 改进路线

| 优先级 | 改进 | 预期收益 |
|--------|------|---------|
| P0 | 启用连续批处理 | 并发吞吐 3-5× |
| P1 | 集成 Prefix Cache | 多轮对话 prefill 省 50-80% |
| P2 | 修复 torch.compile | decode 延迟 -20% |
| P3 | 自研 PagedAttention | KV Cache 利用率 +30% |
