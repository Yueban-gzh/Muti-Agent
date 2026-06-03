"""服务层统一异常，供 API 层转换为 HTTP 响应。"""


class ServiceError(Exception):
    """业务逻辑错误（非系统崩溃）。"""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
