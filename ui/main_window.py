from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
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
        # 左侧导航栏容器
        nav_widget = QWidget()
        nav_layout = QVBoxLayout()
        nav_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        nav_layout.setContentsMargins(15, 20, 15, 20)
        
        # 顶部显示用户头像和用户名
        avatar_label = QLabel()
        avatar_label.setFixedSize(60, 60)
        avatar_label.setStyleSheet("""
            background-color: #4a90e2;
            border-radius: 30px;
            color: white;
            font-size: 24px;
            font-weight: bold;
            qproperty-alignment: AlignCenter;
        """)
        first_char = self.user_info['username'][0].upper() if self.user_info['username'] else "U"
        avatar_label.setText(first_char)
        
        username_label = QLabel(self.user_info['username'])
        username_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 8px;")
        username_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        nav_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        nav_layout.addWidget(username_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # 添加弹性空间，将按钮区域向下推
        nav_layout.addStretch()
        
        # 按钮统一样式：带边框、圆角、内边距
        button_style = """
            QPushButton {
                background-color: white;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                padding: 8px 12px;
                text-align: center;
                font-size: 14px;
                font-weight: normal;
                margin: 4px 0px;
            }
            QPushButton:hover {
                background-color: #f0f2f5;
                border-color: #4a90e2;
            }
            QPushButton:pressed {
                background-color: #e0e4e8;
            }
        """
        
        # 创建新任务按钮
        btn_home = QPushButton("创建新任务")
        btn_home.setStyleSheet(button_style)
        btn_home.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_home.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_widget))
        
        # 历史记录按钮
        btn_history = QPushButton("历史记录")
        btn_history.setStyleSheet(button_style)
        btn_history.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_history.clicked.connect(lambda: self.stack.setCurrentWidget(self.history_widget))
        
        # 退出登录按钮
        logout_btn = QPushButton("退出登录")
        logout_btn.setStyleSheet(button_style)
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.clicked.connect(self.logout)
        
        # 将按钮添加到布局中
        nav_layout.addWidget(btn_home)
        nav_layout.addWidget(btn_history)
        nav_layout.addStretch()   # 在历史记录和退出登录之间加弹性空间
        nav_layout.addWidget(logout_btn)
        
        nav_widget.setLayout(nav_layout)
        nav_widget.setFixedWidth(240)
        nav_widget.setStyleSheet("""
            QWidget {
                background-color: #fafbfc;
                border-right: 1px solid #e1e4e8;
            }
        """)
        
        # 主布局：左侧导航 + 右侧内容
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