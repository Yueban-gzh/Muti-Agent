from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QMessageBox, QTabWidget)
from PyQt6.QtCore import Qt
from ui.real_api.client import RealAPI

class LoginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.api = RealAPI()
        self.setWindowTitle("多智能体决策系统 - 登录")
        self.setFixedSize(400, 300)
        
        self.tabs = QTabWidget()
        self.login_tab = QWidget()
        self.register_tab = QWidget()
        self.tabs.addTab(self.login_tab, "登录")
        self.tabs.addTab(self.register_tab, "注册")
        
        self.init_login_tab()
        self.init_register_tab()
        
        layout = QVBoxLayout()
        layout.addWidget(self.tabs)
        self.setLayout(layout)
    
    def init_login_tab(self):
        layout = QVBoxLayout()
        layout.addStretch()
        
        self.login_username = QLineEdit()
        self.login_username.setPlaceholderText("用户名")
        self.login_password = QLineEdit()
        self.login_password.setPlaceholderText("密码")
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.login_btn = QPushButton("登录")
        self.login_btn.clicked.connect(self.on_login)
        
        layout.addWidget(QLabel("用户名:"))
        layout.addWidget(self.login_username)
        layout.addWidget(QLabel("密码:"))
        layout.addWidget(self.login_password)
        layout.addWidget(self.login_btn)
        layout.addStretch()
        self.login_tab.setLayout(layout)
    
    def init_register_tab(self):
        layout = QVBoxLayout()
        layout.addStretch()
        
        self.reg_username = QLineEdit()
        self.reg_username.setPlaceholderText("用户名")
        self.reg_password = QLineEdit()
        self.reg_password.setPlaceholderText("密码")
        self.reg_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_confirm = QLineEdit()
        self.reg_confirm.setPlaceholderText("确认密码")
        self.reg_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_email = QLineEdit()
        self.reg_email.setPlaceholderText("邮箱（可选）")
        
        self.register_btn = QPushButton("注册")
        self.register_btn.clicked.connect(self.on_register)
        
        layout.addWidget(QLabel("用户名:"))
        layout.addWidget(self.reg_username)
        layout.addWidget(QLabel("密码:"))
        layout.addWidget(self.reg_password)
        layout.addWidget(QLabel("确认密码:"))
        layout.addWidget(self.reg_confirm)
        layout.addWidget(QLabel("邮箱:"))
        layout.addWidget(self.reg_email)
        layout.addWidget(self.register_btn)
        layout.addStretch()
        self.register_tab.setLayout(layout)
    
    def on_login(self):
        username = self.login_username.text().strip()
        password = self.login_password.text().strip()
        if not username or not password:
            QMessageBox.warning(self, "错误", "用户名和密码不能为空")
            return

        # 显示等待提示
        self.login_btn.setEnabled(False)
        self.login_btn.setText("登录中...")

        def login_success(result):
            user_info, token = result
            self.api.set_token(token, user_info)
            from ui.main_window import MainWindow
            self.main_window = MainWindow(user_info, self.api)
            self.main_window.show()
            self.close()

        def login_error(msg):
            self.login_btn.setEnabled(True)
            self.login_btn.setText("登录")
            QMessageBox.warning(self, "错误", msg)
        self.api.login_async(username, password, login_success, login_error)
    
    def on_register(self):
        username = self.reg_username.text().strip()
        pwd = self.reg_password.text().strip()
        confirm = self.reg_confirm.text().strip()
        email = self.reg_email.text().strip()
        if not username or not pwd:
            QMessageBox.warning(self, "错误", "用户名和密码不能为空")
            return
        if pwd != confirm:
            QMessageBox.warning(self, "错误", "两次密码不一致")
            return
        result = self.api.register(username, pwd, email)
        if result and "用户名已存在" not in result.get("message", ""):
            QMessageBox.information(self, "成功", "注册成功，请登录")
            self.tabs.setCurrentIndex(0)
            self.login_username.setText(username)
            self.login_password.clear()
        else:
            QMessageBox.warning(self, "错误", result.get("message", "注册失败"))