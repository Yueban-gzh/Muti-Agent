import random
from PyQt6.QtWidgets import QLineEdit, QPushButton
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QMessageBox, QTabWidget, QGraphicsDropShadowEffect)
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QBrush, QPen, QFont
from ui.config import USE_REAL_API
from ui.real_api.client import RealAPI
from ui.mock_api.client import MockAPI

class PasswordLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setPlaceholderText("密码")
        # 预留右侧空间给图标按钮
        self.setStyleSheet("QLineEdit { padding-right: 32px; }")
        
        # 获取图标文件的绝对路径（根据你的实际存放位置调整）
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.icon_open = QIcon(os.path.join(base_dir, "resources", "open_eye.png"))
        self.icon_closed = QIcon(os.path.join(base_dir, "resources", "closed_eye.png"))
        
        # 创建切换按钮
        self.toggle_btn = QPushButton(self)
        self.toggle_btn.setIcon(self.icon_closed)  # 初始为闭眼（隐藏密码）
        self.toggle_btn.setFixedSize(24, 24)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                background-color: rgba(100, 100, 100, 0.2);
                border-radius: 12px;
            }
        """)
        self.toggle_btn.clicked.connect(self.toggle_visibility)
        self._password_visible = False

    def resizeEvent(self, event):
        """当输入框大小改变时，将按钮定位到右侧中央"""
        super().resizeEvent(event)
        btn_width = self.toggle_btn.width()
        btn_height = self.toggle_btn.height()
        x = self.width() - btn_width - 4  # 距离右边框4像素
        y = (self.height() - btn_height) // 2
        self.toggle_btn.move(x, y)

    def toggle_visibility(self):
        if self._password_visible:
            self.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_btn.setIcon(self.icon_closed)
            self._password_visible = False
        else:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_btn.setIcon(self.icon_open)
            self._password_visible = True

# ==================== 左侧：动态科技感粒子背景控件 ====================
class TechGraphicsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(350)
        self.particles = []
        for _ in range(25):
            self.particles.append({
                "pos": QPointF(random.randint(10, 340), random.randint(10, 540)),
                "speed": QPointF(random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5)),
                "radius": random.uniform(2, 4)
            })
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_particles)
        self.timer.start(30)

    def update_particles(self):
        for p in self.particles:
            p["pos"].setX(p["pos"].x() + p["speed"].x())
            p["pos"].setY(p["pos"].y() + p["speed"].y())
            if p["pos"].x() < 0 or p["pos"].x() > self.width(): p["speed"].setX(-p["speed"].x())
            if p["pos"].y() < 0 or p["pos"].y() > self.height(): p["speed"].setY(-p["speed"].y())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor("#0f131e")) 
        gradient.setColorAt(1.0, QColor("#171d2c"))
        painter.fillRect(self.rect(), QBrush(gradient))

        pen = QPen()
        for i, p1 in enumerate(self.particles):
            for p2 in self.particles[i+1:]:
                dist = (p1["pos"] - p2["pos"]).manhattanLength()
                if dist < 100:
                    alpha = int((1.0 - dist / 100) * 50)
                    pen.setColor(QColor(184, 154, 106, alpha)) 
                    pen.setWidthF(0.8)
                    painter.setPen(pen)
                    painter.drawLine(p1["pos"], p2["pos"])

        painter.setPen(Qt.PenStyle.NoPen)
        for p in self.particles:
            glow_color = QColor("#b89a6a")
            glow_color.setAlpha(130)
            painter.setBrush(QBrush(glow_color))
            painter.drawEllipse(p["pos"], p["radius"], p["radius"])

        painter.setPen(QColor("#f5edd7"))
        font = QFont("Microsoft YaHei", 22, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "多智能体\n决策系统\n\n—")


# ==================== 主登录窗口 ====================
class LoginWidget(QWidget):
    def __init__(self):
        super().__init__()
        if USE_REAL_API:
            self.api = RealAPI()
        else:
            self.api = MockAPI()
            
        self.setWindowTitle("多智能体决策系统 - 登录")
        self.setFixedSize(780, 550)
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.left_panel = TechGraphicsWidget()
        main_layout.addWidget(self.left_panel, stretch=4)
        
        self.right_panel = QWidget()
        self.right_panel.setObjectName("right_panel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(45, 40, 45, 40)
        
        welcome_label = QLabel("欢迎回来")
        welcome_label.setObjectName("welcome_label")
        sub_label = QLabel("请验证或注册您的智能体管理账户")
        sub_label.setObjectName("sub_label")
        right_layout.addWidget(welcome_label)
        right_layout.addWidget(sub_label)
        
        self.tabs = QTabWidget()
        self.login_tab = QWidget()
        self.register_tab = QWidget()
        self.login_tab.setObjectName("login_tab")
        self.register_tab.setObjectName("register_tab")
        
        self.tabs.addTab(self.login_tab, " 登录账户 ")
        self.tabs.addTab(self.register_tab, " 注册新用户 ")
        
        self.init_login_tab()
        self.init_register_tab()
        
        right_layout.addWidget(self.tabs)
        main_layout.addWidget(self.right_panel, stretch=5)
        
        self.setLayout(main_layout)

        # 右侧面板微弱的暗色呼吸灯
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_right_panel_color)
        self.val = 18
        self.direction = 1
        self.animation_timer.start(100)

    def _update_right_panel_color(self):
        self.val += 0.05 * self.direction
        if self.val >= 21 or self.val <= 16:
            self.direction *= -1
        color = QColor.fromHsv(220, 30, int(self.val))
        palette = self.right_panel.palette()
        palette.setColor(self.right_panel.backgroundRole(), color)
        self.right_panel.setPalette(palette)
        self.right_panel.setAutoFillBackground(True)

    def init_login_tab(self):
        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(0, 20, 0, 0)
        
        self.login_username = QLineEdit()
        self.login_username.setPlaceholderText("请输入用户名")
        self.login_username.setObjectName("login_username")
        
        self.login_password = PasswordLineEdit()
        self.login_password.setPlaceholderText("请输入密码")
        
        self.login_password.setObjectName("login_password")
        
        self.login_btn = QPushButton("进入决策核心")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(self.on_login)
        # 注意：移除了 pressed 信号，避免样式被清空和按钮变大
        
        layout.addWidget(QLabel("用户名"))
        layout.addWidget(self.login_username)
        layout.addWidget(QLabel("安全密码"))
        layout.addWidget(self.login_password)
        layout.addSpacing(15)
        layout.addWidget(self.login_btn)
        layout.addStretch()
        self.login_tab.setLayout(layout)

        self._setup_focus_effect(self.login_username)
        self._setup_focus_effect(self.login_password)

    def init_register_tab(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(0, 15, 0, 0)
        
        self.reg_username = QLineEdit()
        self.reg_username.setPlaceholderText("设定登录用户名")
        self.reg_password = PasswordLineEdit()
        self.reg_password.setPlaceholderText("强密码（英文字母+数字）")
        
        self.reg_confirm = PasswordLineEdit()
        self.reg_confirm.setPlaceholderText("请再次输入密码")
        
        self.reg_email = QLineEdit()
        self.reg_email.setPlaceholderText("用于安全密钥找回（可选）")
        
        self.register_btn = QPushButton("完成建立智能体账户")
        self.register_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.register_btn.clicked.connect(self.on_register)
        # 同样移除 pressed 信号
        
        layout.addWidget(QLabel("用户名 *"))
        layout.addWidget(self.reg_username)
        layout.addWidget(QLabel("密码 *"))
        layout.addWidget(self.reg_password)
        layout.addWidget(QLabel("确认密码 *"))
        layout.addWidget(self.reg_confirm)
        layout.addWidget(QLabel("安全邮箱"))
        layout.addWidget(self.reg_email)
        layout.addSpacing(12)
        layout.addWidget(self.register_btn)
        layout.addStretch()
        self.register_tab.setLayout(layout)

        self._setup_focus_effect(self.reg_username)
        self._setup_focus_effect(self.reg_password)
        self._setup_focus_effect(self.reg_confirm)
        self._setup_focus_effect(self.reg_email)

    def _setup_focus_effect(self, widget):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor("#b89a6a"))
        shadow.setOffset(0, 0)
        shadow.setEnabled(False)
        widget.setGraphicsEffect(shadow)

        orig_focus_in = widget.focusInEvent
        orig_focus_out = widget.focusOutEvent

        def custom_focus_in(event):
            shadow.setEnabled(True)
            orig_focus_in(event)

        def custom_focus_out(event):
            shadow.setEnabled(False)
            orig_focus_out(event)

        widget.focusInEvent = custom_focus_in
        widget.focusOutEvent = custom_focus_out

    # ========== 原有登录/注册逻辑（未改动） ==========
    def on_login(self):
        username = self.login_username.text().strip()
        password = self.login_password.text().strip()
        if not username or not password:
            QMessageBox.warning(self, "错误", "用户名和密码不能为空")
            return

        if USE_REAL_API:
            self.login_btn.setEnabled(False)
            self.login_btn.setText("正在接入节点...")

            def login_success(result):
                user_info, token = result
                self.api.set_token(token, user_info)
                from ui.main_window import MainWindow
                self.main_window = MainWindow(user_info, self.api)
                self.main_window.show()
                self.close()

            def login_error(msg):
                self.login_btn.setEnabled(True)
                self.login_btn.setText("进入决策核心")
                QMessageBox.warning(self, "错误", msg)

            self.api.login_async(username, password, login_success, login_error)
        else:
            result = self.api.login(username, password)
            if result and result.get("access_token"):
                user_info = self.api.get_current_user()
                if user_info:
                    from ui.main_window import MainWindow
                    self.main_window = MainWindow(user_info, self.api)
                    self.main_window.show()
                    self.close()
                else:
                    QMessageBox.warning(self, "错误", "获取用户信息失败")
            else:
                QMessageBox.warning(self, "错误", "用户名或密码错误")

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