from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTableWidget,
                             QTableWidgetItem, QPushButton, QHeaderView, QMessageBox)
from PyQt6.QtCore import Qt

class UserHistoryWidget(QWidget):
    def __init__(self, user_info, api_client, stack, result_widget):
        super().__init__()
        self.user_info = user_info
        self.api = api_client
        self.stack = stack
        self.result_widget = result_widget
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        title = QLabel("历史决策记录")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["任务ID", "决策问题", "创建时间", "查看详情"])
        header = self.table.horizontalHeader()
    # 设置各列宽度模式
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # 任务ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)           # 决策问题
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # 创建时间
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)             # 查看详情
        self.table.setColumnWidth(3, 100)  # 固定宽度 100 像素

        layout.addWidget(self.table)
        self.setLayout(layout)

    def showEvent(self, event):
        self.load_history()
        super().showEvent(event)

    def load_history(self):
        tasks = self.api.get_my_history()
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            # 使用 "id" 而不是 "task_id"
            self.table.setItem(row, 0, QTableWidgetItem(str(task["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(task["question"]))
            self.table.setItem(row, 2, QTableWidgetItem(task["created_at"]))
            btn = QPushButton("查看结果")
            btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                font-weight: bold;
                color: #0f172a;
                background-color: #94a3b8;
                border: 1px solid #94a3b8;  /* 这里可以改成更细，比如 1px 或 0.5px */
                border-radius: 5px;          /* 可以改小圆角 */
                padding: 4px 8px;            /* 内边距调整 */
            }
            QPushButton:hover {
                background-color: #e4b35f;
                border-color: #f59e0b;
                color: #000000;
            }
            QPushButton:pressed {
                background-color: #b45309;
                border-color: #b45309;
            }
            QPushButton:disabled {
                background-color: #475569;
                border-color: #475569;
                color: #94a3b8;
            }
           """)    
            btn.setMinimumWidth(80)
            btn.setMinimumHeight(24)
            btn.clicked.connect(lambda checked, t=task: self.view_result(t))
            self.table.setCellWidget(row, 3, btn)

    def view_result(self, task):
        task_id = task["id"]
        status = task.get("status")  # 确保历史列表中有 status 字段
        if status == "completed":
            task_detail = self.api.get_debate_result(task_id)
            if task_detail:
                self.result_widget.load_history_result(task_id, task_detail, show_export=True)
                self.stack.setCurrentWidget(self.result_widget)
            else:
                QMessageBox.warning(self, "错误", "无法获取该任务的结果")
        elif status in ("discussing", "finalizing"):
            from ui.discussion_widget import DiscussionWidget
            # 检查是否已存在该任务的讨论室
            for i in range(self.stack.count()):
                w = self.stack.widget(i)
                if isinstance(w, DiscussionWidget) and hasattr(w, 'task_id') and w.task_id == task_id:
                    self.stack.setCurrentWidget(w)
                    return
            discussion_widget = DiscussionWidget(
                self.user_info, self.api, self.stack,
                task_id, task["question"], task.get("decision_mode", "multi_angle")
            )
            self.stack.addWidget(discussion_widget)
            self.stack.setCurrentWidget(discussion_widget)
        else:
            QMessageBox.warning(self, "错误", "无法查看该任务")
