# Jixia 多智能体决策辅助系统 — 新手启动指南

## 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│  你的电脑 (Windows)                                              │
│                                                                  │
│  PyQt6 桌面应用 ──→ FastAPI 后端 (:8000) ──→ SSH 隧道 (:30000)   │
│  (ui/main.py)      (backend/main.py)       ssh -L 30000:...      │
└──────────────────────────────────────────────────────────────────┘
                                                   │
                                          ssh -p 37096 -L
                                                   │
                                          ┌────────┴──────────┐
                                          │  GPU 服务器         │
                                          │  10.112.247.63     │
                                          │  Hunyuan-7B        │
                                          │  GPTQ-INT4 (:30000) │
                                          └───────────────────┘
```

---

## 第一次使用（环境安装，只需一次）

### 本地

```powershell
cd d:\jixia-Python
pip install fastapi "uvicorn[standard]" sqlalchemy aiosqlite httpx pyjwt bcrypt sentence-transformers PyQt6 matplotlib numpy pandas requests
```

### 服务器

```bash
ssh -p 37096 root@10.112.247.63
# 密码: 123

source /root/miniconda3/bin/activate bnn

# 检查是否缺包（一般已装好）
pip install gptqmodel optimum accelerate -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/
```

---

## 每次启动（三步）

### 1️⃣ 启动远程推理服务

```bash
ssh -p 37096 root@10.112.247.63

cd /ai/data/lyr/sglang
source /root/miniconda3/bin/activate bnn
export PYTHONPATH=/ai/data/lyr/sglang

nohup python -m backend.inference.cli \
    --model-path /ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4 \
    --host 0.0.0.0 --port 30000 \
    --max-batch-size 4 --no-compile \
    > server_jixia.log 2>&1 &

# 等 30 秒
tail -f server_jixia.log
# 看到 "Uvicorn running on http://0.0.0.0:30000" 即成功
```

### 2️⃣ 建立 SSH 隧道（新终端，保持打开）

```powershell
ssh -p 37096 -L 30000:127.0.0.1:30000 root@10.112.247.63
```

> 输入密码后别关这个窗口，它把远程 30000 端口映射到本地 30000。

### 3️⃣ 启动本地后端 + UI

**终端 A — 后端：**
```powershell
cd d:\jixia-Python\backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 后——

**终端 B — 桌面应用：**
```powershell
cd d:\jixia-Python
python -m ui.main
```

---

## 切换 LLM（可选）

编辑 `os.env`：

```ini
# 用本地推理（当前配置）
LLM_BACKEND=api
DEEPSEEK_BASE_URL=http://127.0.0.1:30000/v1
DEEPSEEK_MODEL=default

# 切回 DeepSeek（取消下面注释，注释上面三行）
# DEEPSEEK_BASE_URL=https://www.sophnet.com/api/open-apis/v1
# DEEPSEEK_MODEL=DeepSeek-V4-Flash
```

---

## 常见问题

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError: No module named 'api'` | 必须从 `backend/` 目录启动 |
| 推理返回空 / 连接超时 | 检查隧道是否开着，`ssh -p 37096 -L ...` |
| 端口 30000 被占用 | 服务器上 `pkill -9 -f backend.inference` 后重启 |
| 推理挂了 | SSH 到服务器看 `tail -50 /ai/data/lyr/sglang/server_jixia.log` |
| 端口 8000 被占用 | `netstat -ano \| findstr 8000`，`taskkill /PID xxx` |

---

## 自研推理引擎

项目自主实现了 OpenAI 兼容的推理引擎（`backend/inference/`），替代 SGLang/vLLM，直接调用 `transformers` + `gptqmodel` 加载 Hunyuan-7B GPTQ-INT4 模型。详细设计见 `backend/inference/engine.py` 和 `memory.md` 第 9 节。
