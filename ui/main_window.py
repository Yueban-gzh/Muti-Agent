import os  # 新增导入，用于处理路径
from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel, QButtonGroup
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMovie  # 新增导入
from ui.user_home_widget import UserHomeWidget
from ui.user_result_widget import UserResultWidget
from ui.user_history_widget import UserHistoryWidget
from ui.admin_widget import AdminWidget

class MainWindow(QMainWindow):
    def __init__(self, user_info: dict, api_client):
        super().__init__()
        self.user_info = user_info
        self.api = api_client
        self.setWindowTitle(f"多智能体决策系统 - {user_info['username']} ({user_info['role']})")
        self.setGeometry(100, 100, 1200, 800)
        
        self.stack = QStackedWidget()
        
        if user_info['role'] == 'admin':
            self.admin_widget = AdminWidget(user_info, self.api, self.stack)
            self.stack.addWidget(self.admin_widget)
            self.setCentralWidget(self.stack)
        else:
            # 普通用户：创建页面
            self.result_widget = UserResultWidget(user_info, self.api, self.stack)
            self.history_widget = UserHistoryWidget(user_info, self.api, self.stack, self.result_widget)
            self.home_widget = UserHomeWidget(user_info, self.api, self.stack, self.result_widget)
            
            self.stack.addWidget(self.home_widget)
            self.stack.addWidget(self.result_widget)
            self.stack.addWidget(self.history_widget)
            self.stack.setCurrentWidget(self.home_widget)
            
            self.setup_navbar()
    
    def setup_navbar(self):
        nav_widget = QWidget()
        nav_layout = QVBoxLayout()
        nav_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # 调整了边距，让按钮能贴到边框，更有“横条”感
        nav_layout.setContentsMargins(0, 24, 0, 24)
        nav_layout.setSpacing(4) # 按钮之间的微小间距

        # --- 1. 用户信息区域 ---
        avatar_label = QLabel()
        avatar_label.setFixedSize(60, 60)
        avatar_label.setStyleSheet("""
            background-color: #b89a6a;
            border-radius: 30px;
            color: #0f172a;
            font-size: 24px;
            font-weight: bold;
            qproperty-alignment: AlignCenter;
        """)
        first_char = self.user_info['username'][0].upper() if self.user_info['username'] else "U"
        avatar_label.setText(first_char)

        username_label = QLabel(self.user_info['username'])
        username_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 8px; margin-bottom: 20px; color: #fbbf24;")
        username_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nav_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        nav_layout.addWidget(username_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # --- 2. 核心样式表定义 ---
        button_style = """
            QPushButton {
                background-color: transparent;
                color: #94a3b8;
                border: none;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 14px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #1e293b;
                color: #f8fafc;
            }
            QPushButton:checked {
                background-color: #e4b35f;
                color: #0f172a;
            }
        """
        
        logout_button_style = """
            QPushButton {
                background-color: #1e293b;
                color: #ef4444;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 14px;
                margin: 0 16px;
            }
            QPushButton:hover {
                background-color: #dc2626;
                color: #ffffff;
            }
        """

        # --- 3. 创建导航按钮组（实现互斥高亮） ---
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True) # 开启互斥功能

        btn_home = QPushButton("  创建新任务")
        btn_home.setStyleSheet(button_style)
        btn_home.setCheckable(True)
        btn_home.setChecked(True) # 默认首页选中
        btn_home.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_widget))
        self.nav_group.addButton(btn_home)

        btn_history = QPushButton("  历史记录")
        btn_history.setStyleSheet(button_style)
        btn_history.setCheckable(True)
        btn_history.clicked.connect(lambda: self.stack.setCurrentWidget(self.history_widget))
        self.nav_group.addButton(btn_history)

        # 将导航菜单加入布局
        nav_layout.addWidget(btn_home)
        nav_layout.addWidget(btn_history)
        # 添加一个弹簧，将下面内容推到底部（这样才能让 GIF 和退出按钮紧贴底部）
        nav_layout.addStretch()

        # ========= 添加 GIF 动图 =========
        # 构造 GIF 文件的绝对路径（位于 ui/resources/test.gif）
        current_dir = os.path.dirname(os.path.abspath(__file__))
        gif_path = os.path.join(current_dir, "resources", "test.gif")
        
        gif_label = QLabel()
        # 设置方形大小，例如 120x120（可根据需要调整）
        square_size = 200
        gif_label.setFixedSize(square_size, square_size)
        gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gif_label.setScaledContents(True)  # 让 GIF 填充整个 label（保持方形填充，如果 GIF 也是方形不会变形）
        # 或者使用 QMovie 的 setScaledSize，两者均可
        movie = QMovie(gif_path)
        movie.setScaledSize(gif_label.size())
        gif_label.setMovie(movie)
        movie.start()

        # 添加 GIF 到布局，水平居中
        nav_layout.addWidget(gif_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 退出按钮
        logout_btn = QPushButton("退出登录")
        logout_btn.setStyleSheet(logout_button_style)
        logout_btn.clicked.connect(self.logout)
        nav_layout.addWidget(logout_btn)

        # 可以再加一个小弹簧，让退出按钮离 GIF 有一点呼吸空间（可选，不挨着则去掉即可）
        nav_layout.addSpacing(0)  # 不加额外间距，就是紧挨着

        # 侧边栏整体背景
        nav_widget.setLayout(nav_layout)
        nav_widget.setFixedWidth(240)
        nav_widget.setStyleSheet("""
            QWidget {
                background-color: #0f172a;
                border-right: 1px solid #334155;
            }
        """)

        # 组装主布局
        main_layout = QHBoxLayout()
        main_layout.addWidget(nav_widget)
        main_layout.addWidget(self.stack)
        main_layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def logout(self):
        self.api.logout()
        from ui.login_widget import LoginWidget
        self.login_window = LoginWidget()
        self.login_window.show()
        self.close()