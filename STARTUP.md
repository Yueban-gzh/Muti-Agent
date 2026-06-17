# Jixia 多智能体决策辅助系统 — 启动指南

## 架构

```
PyQt6 UI ──→ FastAPI 后端 (:8000) ──→ SSH 隧道 (:30000) ──→ GPU 服务器 Hunyuan-7B
 本地          本地                      本地                   远程 10.112.247.63
```

---

## 环境安装（只需一次）

### 本地

```powershell
cd d:\jixia-Python
pip install fastapi "uvicorn[standard]" sqlalchemy aiosqlite httpx pyjwt bcrypt sentence-transformers PyQt6 matplotlib numpy pandas requests
```

### 服务器

```bash
ssh -p 37096 root@10.112.247.63   # 密码: 123

source /root/miniconda3/bin/activate bnn
pip install gptqmodel -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/
```

---

## 每次启动（按顺序执行）

### 1. 启动远程推理服务

```bash
ssh -p 37096 root@10.112.247.63   # 密码: 123

cd /ai/data/lyr/sglang
source /root/miniconda3/bin/activate bnn
export PYTHONPATH=/ai/data/lyr/sglang

pkill -9 -f "backend.inference" 2>/dev/null; sleep 1

nohup python -m backend.inference.cli \
    --model-path /ai/data/lyr/sglang/models/Hunyuan-7B-Instruct-GPTQ-Int4 \
    --host 0.0.0.0 --port 30000 \
    --max-batch-size 4 --no-compile \
    > server_jixia.log 2>&1 &

tail -f server_jixia.log
# 等到出现 "Uvicorn running on http://0.0.0.0:30000"，Ctrl+C 退出 tail
```

### 2. 建立 SSH 隧道（新开终端，保持打开）

```powershell
ssh -p 37096 -L 30000:127.0.0.1:30000 root@10.112.247.63
# 密码: 123，输入后别关这个窗口
```

### 3. 启动本地后端（新开终端）

```powershell
cd d:\jixia-Python\backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
# 等到出现 "Uvicorn running on http://127.0.0.1:8000"
```

### 4. 启动桌面应用（新开终端）

```powershell
cd d:\jixia-Python
python -m ui.main
```

---

## 切换 LLM

编辑项目根目录 `os.env`：

```ini
# 使用自研推理（当前配置）
LLM_BACKEND=api
DEEPSEEK_BASE_URL=http://127.0.0.1:30000/v1
DEEPSEEK_MODEL=default

# 切回 DeepSeek
# DEEPSEEK_BASE_URL=https://www.sophnet.com/api/open-apis/v1
# DEEPSEEK_MODEL=DeepSeek-V4-Flash
```

---

## 常见问题

| 问题 | 解决 |
|------|------|
| 推理返回空 / 连接超时 | 检查第 2 步隧道是否开着 |
| `ModuleNotFoundError: No module named 'api'` | 后端必须从 `backend/` 目录启动 |
| 端口 30000 被占用 | 服务器上 `pkill -9 -f backend.inference` |
| 端口 8000 被占用 | `netstat -ano \| findstr 8000`，`taskkill /PID xxx` |
| GitHub push 被墙 | `git config http.proxy http://127.0.0.1:7892` |
