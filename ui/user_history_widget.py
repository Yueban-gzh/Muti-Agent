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
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def showEvent(self, event):
        self.load_history()
        super().showEvent(event)

    def load_history(self):
        tasks = self.api.get_my_history()
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.table.setItem(row, 0, QTableWidgetItem(str(task["task_id"])))
            self.table.setItem(row, 1, QTableWidgetItem(task["question"]))
            self.table.setItem(row, 2, QTableWidgetItem(task["created_at"]))
            btn = QPushButton("查看结果")
            btn.clicked.connect(lambda checked, t=task: self.view_result(t))
            self.table.setCellWidget(row, 3, btn)

    def view_result(self, task):
        task_detail = self.api.get_debate_result(task["task_id"])
        if task_detail:
            self.result_widget.load_history_result(task["task_id"], task_detail, show_export=True)
            self.stack.setCurrentWidget(self.result_widget)
        else:
            QMessageBox.warning(self, "错误", "无法获取该任务的结果")