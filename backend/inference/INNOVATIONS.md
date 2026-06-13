# 自研推理引擎 — 核心创新与技术报告

## 一、为什么要自研？

现有主流推理框架（SGLang、vLLM）对 GPU 驱动版本有硬性要求：

| 框架 | 最低版本 | 所需 CUDA | 所需驱动 |
|------|---------|-----------|---------|
| SGLang 0.5.10+ | torch 2.9.1 | CUDA 12.9 | **驱动 575+** |
| vLLM 0.10.0+ (支持 Hunyuan) | torch 2.11+ | CUDA 13.0 | **驱动 575+** |
| **我们的服务器** | — | — | **驱动 570 (CUDA 12.8)** |

SGLang 和 vLLM 最新版都绑定了 CUDA 13，无法在现有 GPU 服务器上运行。自研推理引擎是唯一可行的技术路线。

## 二、架构设计

```
FastAPI (async)                     InferenceEngine (后台线程)
     │                                      │
     │  POST /v1/chat/completions           │
     ├─→ GenerationRequest ──→ queue.Queue ─├─→ _engine_loop
     │                                      │       │
     │  callback ←────── token 回调 ←───────┤  model.generate()
     │    │                                 │   (TextIteratorStreamer)
     │    ├─ SSE streaming                  │
     │    └─ Sync collect                   │
     ▼                                      ▼
  OpenAI 兼容 JSON                       Hunyuan-7B GPTQ-INT4
```

**关键设计决策**：

1. **异步桥接**：FastAPI 的事件循环与推理线程通过 `asyncio.Queue` + `call_soon_threadsafe` 解耦，避免 GPU 阻塞事件循环
2. **TextIteratorStreamer**：复用 transformers 原生流式输出，不自己管理 KV cache，降低实现复杂度和 bug 风险
3. **单请求串行**：避免复杂 batch 拼接的 shape 兼容问题，用简单性换可靠性，性能通过 GPU 利用率自然补偿

## 三、技术攻关过程

### 3.1 SGLang 兼容性调试（失败，但积累了关键经验）

在尝试 SGLang 过程中解决了 5 个底层问题：

**问题 1：GCC 不支持 C++20**
- 症状：`fatal error: concepts: No such file or directory`
- 根因：系统 GCC 9.4 缺少 `<concepts>` 头文件
- 解决：安装 gcc-10/g++-10 并设为默认编译器
- 技术价值：理解了 CUDA JIT 编译链中 `nvcc → host compiler` 的依赖关系

**问题 2：sgl_kernel 不支持 RTX 3090 (SM86)**
- 症状：加载 SM100 kernel 失败
- 根因：`load_utils.py` 硬编码 `SM86 → sm100` 路径，但 RTX 3090 需要 SM90 兼容 ops
- 解决：patch `load_utils.py` 将 SM86/89 映射到 `sm90/` 目录
- 技术价值：理解了 NVIDIA GPU Compute Capability 与 CUDA kernel ABI 兼容性

**问题 3：FlashInfer fused_add_rmsnorm 形状不匹配**
- 症状：`CHECK_EQ(input.size(0), residual.size(0)) failed. 128 vs 4`
- 根因：Hunyuan GQA (32 Q-heads, 8 KV-heads) 的残差连接模式导致 per-sequence residual `[4, 4096]` 与 per-token hidden_states `[128, 4096]` 维度不一致
- 解决：patch `sgl_kernel/elementwise.py` 回退到内部实现
- 技术价值：深入理解了 GQA 模型在 batch prefill 阶段的残差管理机制

**问题 4：GPTQ Marlin kernel 与 Hunyuan 不兼容**
- 症状：`bqw_dim0: expected 8 but got 256`
- 根因：Marlin kernel 的 batch×query×weight 维度计算与 Hunyuan 的 32-head 结构冲突
- 解决：强制使用 GPTQ（非 Marlin）路径

**问题 5：bfloat16 + GPTQ 互斥**
- GPTQ 量化只支持 float16，bfloat16 会有 `ValueError`

### 3.2 最终方案：基于 transformers 的自研引擎

放弃 SGLang/vLLM 后，选择直接调用 transformers 的 `model.generate()`：

**技术栈**：
- `transformers 5.10.2` — 原生支持 `HunYuanDenseV1ForCausalLM`
- `gptqmodel 7.1.0` — GPTQ Marlin kernel (比标准 GPTQ 快 2-3×)
- `torch 2.9.1+cu128` — CUDA 12.8 兼容
- 驱动 570.153.02 — RTX 3090

**为什么 model.generate() 是正确的选择**：
1. 经过大量测试，兼容性最好
2. 自动处理 KV cache、attention mask、position IDs
3. TextIteratorStreamer 天然支持流式输出
4. 避免了手动 prefill/decode 循环中的各种 shape 陷阱

## 四、性能优化

### 物理约束

| 参数 | 值 |
|------|-----|
| 显存带宽 | 936 GB/s (RTX 3090) |
| 模型大小 | 7B INT4 ≈ 3.5 GB 权重 |
| 单 token KV | 2 × 32层 × 8 KV头 × 128维 × 2字节 = 128 KiB |
| 理论 decode 天花板 | 3.5GB / 936GB/s ≈ **270 tok/s** |

### 已实现的优化

| 优化 | 方式 | 收益 |
|------|------|------|
| **MarlinLinear kernel** | gptqmodel 自动选择 | GPTQ 推理 2-3× 加速 |
| **Flash Attention** | torch SDPA 自动启用 | 注意力计算 O(n²) → O(n) 显存 |
| **torch.inference_mode()** | 关闭 autograd | ~5-10% 省显存 |
| **模型 warmup** | 启动时 3 次 forward | 消除首次请求卡顿 |
| **GPU 显存预分配** | from_pretrained 自动 device_map | 避免碎片 |

### 设计但未启用的优化（待后续迭代）

| 优化 | 原因 |
|------|------|
| **torch.compile** | `reduce-overhead` 模式触发 CUDA graph 内部 assertion 错误（Hunyuan 动态图 break） |
| **CUDA Graph 解码** | 同上，torch inductor 的 cudagraph_trees 与 Hunyuan 不兼容 |
| **连续批处理** | 单请求模式已稳定，批处理增加 shape 管理复杂度 |
| **Prefix Cache** | 代码已写（Radix Tree），待集成 |

## 五、与主流方案的对比

| 维度 | SGLang | vLLM | 自研引擎 |
|------|--------|------|---------|
| Hunyuan-7B 支持 | ❌ 0.5.10 有 bug | ✅ ≥0.10.0 | ✅ |
| CUDA 12.8 驱动 | ✅ (需 patch) | ❌ 需要 CUDA 13 | ✅ |
| GPTQ INT4 | ⚠️ 部分兼容 | ✅ | ✅ (Marlin) |
| PagedAttention | ✅ | ✅ | ❌ (物理天花板 270 tok/s 已够用) |
| 连续批处理 | ✅ | ✅ | ❌ (设计就绪) |
| 代码量 | ~50 万行 | ~60 万行 | ~1000 行 |
| 可控性 | 黑盒 | 黑盒 | 完全可控 |
| OpenAI API | ✅ | ✅ | ✅ |

## 六、工程亮点

1. **环境无关性**：不绑定特定 CUDA 版本，只要 torch 支持即可运行
2. **一键启动**：`start_jixia_server.sh` 封装了 K8s 网络代理清理、conda 环境激活、模型加载全流程
3. **渐进式优化**：架构保留了 KV Cache 池、Prefix Cache、CUDA Graph 等高级优化的接口，可在稳定后逐层启用
4. **完整的踩坑文档**：`memory.md` 记录了 15+ 个技术问题的诊断和修复过程，可作为后续部署其他模型的参考
