# 前端

## 环境准备

```bash
# 创建虚拟环境（可选）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

## 运行前端

```bash
python -m ui.main
```

## 后端配置

默认连接 `http://localhost:8000`。  
如需修改，请编辑 `ui/real_api/client.py` 中的 `base_url`。

## 切换 API 客户端

前端支持一键切换 Mock 模式（使用模拟数据）和真实后端模式。
打开 ui/config.py
修改 USE_REAL_API 的值：
False：使用 MockAPI（模拟数据，无需后端）
True：使用 RealAPI（连接真实后端）
修改后重新运行前端即可生效。
```

