# ui/discussion_widget.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

# 颜色池，用于不同 Agent
AGENT_COLORS = ["#b89a6a", "#80745F", "#699377", "#5e8c8c", "#6b7280"]

class MessageBubble(QWidget):
    def __init__(self, role, content, time_str="", agent_name=""):
        super().__init__()
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(10, 4, 10, 4)

        bubble = QFrame()
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        bubble_layout.setSpacing(2)

        title = QLabel()
        if role == "user":
            title.setText(f"我 · {time_str}")
        elif role == "agent":
            title.setText(f"{agent_name} · {time_str}")
        else:
            title.setText(f"系统 · {time_str}")

        title.setStyleSheet("color:#cbd5e1; font-size:11px; font-weight:bold; background:transparent;")

        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_label.setStyleSheet("color:white; background:transparent; font-size:13px;")

        bubble_layout.addWidget(title)
        bubble_layout.addWidget(content_label)

        # 根据角色调整气泡颜色和对齐
        if role == "user":
            bubble.setStyleSheet("QFrame{background:#687BA6; border-radius:16px;}")
            outer_layout.addStretch()
            outer_layout.addWidget(bubble)
        elif role == "agent":
            idx = abs(hash(agent_name)) % len(AGENT_COLORS)
            color = AGENT_COLORS[idx]
            bubble.setStyleSheet(f"QFrame{{background:{color}; border-radius:16px;}}")
            outer_layout.addWidget(bubble)
            outer_layout.addStretch()
        else:
            bubble.setStyleSheet("QFrame{background:#334155; border-radius:16px;}")
            outer_layout.addStretch()
            outer_layout.addWidget(bubble)
            outer_layout.addStretch()

        bubble.setMaximumWidth(700)


class DiscussionWidget(QWidget):
    def __init__(self, user_info, api_client, stack, task_id, question, decision_mode):
        super().__init__()
        self.user_info = user_info
        self.api = api_client
        self.stack = stack
        self.task_id = task_id
        self.question = question
        self.decision_mode = decision_mode
        self.poll_timer = None

        self.init_ui()
        self.load_messages()
        self.auto_send_initial_message()
        self.start_polling()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # 标题栏
        title_layout = QHBoxLayout()
        title = QLabel(f"讨论室 - {self.question[:80]}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_layout.addWidget(title)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 消息区 - QScrollArea
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea{border:none; background:#1e293b;}")
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.scroll_area)

        # 输入区
        input_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入你的观点...")
        self.input_edit.returnPressed.connect(self.send_message)
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        # 底部按钮
        btn_layout = QHBoxLayout()
        self.exchange_btn = QPushButton("辩手交锋")
        btn_layout.addStretch()
        self.exchange_btn.clicked.connect(self.agent_exchange)
        self.exchange_btn.setVisible(self.decision_mode == "debate")
        self.finalize_btn = QPushButton("结束讨论")
        self.finalize_btn.clicked.connect(self.finalize)
        btn_layout.addWidget(self.exchange_btn)
        btn_layout.addWidget(self.finalize_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def load_messages(self):
        messages = self.api.get_messages(self.task_id)
        self.display_messages(messages)

    def auto_send_initial_message(self):
        # 检查当前是否已有任何消息（除了可能的系统提示）
        messages = self.api.get_messages(self.task_id)
        if not messages:
            # 发送一条默认消息，触发 Agent 首次回复
            initial_content = "请各位专家对当前问题给出初步分析。"
            reply_scope = "all_brief" if self.decision_mode != "debate" else "debate_round"
            success = self.api.send_message(self.task_id, initial_content, reply_scope)
            if success:
                # 发送成功后立即刷新消息
                self.load_messages()
    def display_messages(self, messages):
        # 清空旧消息
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 新消息
        for msg in messages:
            role = msg.get("role", "")
            agent_name = msg.get("agent_name", "")
            content = msg.get("content", "")
            created_at = msg.get("created_at", "")
            time_str = created_at.split("T")[1][:5] if "T" in created_at else ""

            bubble = MessageBubble(role, content, time_str, agent_name)
            self.chat_layout.addWidget(bubble)

        # 自动滚动到底部
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def send_message(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        reply_scope = "all_brief" if self.decision_mode != "debate" else "debate_round"
        success = self.api.send_message(self.task_id, text, reply_scope)
        if success:
            self.input_edit.clear()
            self.load_messages()
        else:
            QMessageBox.warning(self, "错误", "发送失败")

    def agent_exchange(self):
        success = self.api.agent_exchange(self.task_id)
        if success:
            self.load_messages()
        else:
            QMessageBox.warning(self, "错误", "交锋失败")

    def finalize(self):
        self.finalize_btn.setEnabled(False)
        self.finalize_btn.setText("正在生成报告...")
        result = self.api.finalize_task(self.task_id)
        if result and result.get("status") == "completed":
            self.finish_and_show_result()
        else:
            QMessageBox.warning(self, "错误", "结束讨论失败，请重试")
            self.finalize_btn.setEnabled(True)
            self.finalize_btn.setText("生成正式报告")

    def finish_and_show_result(self):
        result_data = self.api.get_debate_result(self.task_id)
        if not result_data:
            QMessageBox.warning(self, "错误", "无法获取分析结果")
            self.finalize_btn.setEnabled(True)
            self.finalize_btn.setText("生成正式报告")
            return

        for i in range(self.stack.count()):
            w = self.stack.widget(i)
            if w.__class__.__name__ == "UserResultWidget":
                w.load_result(self.task_id, result_data, show_export=False)
                self.stack.setCurrentWidget(w)
                return

        from ui.user_result_widget import UserResultWidget
        result_widget = UserResultWidget(self.user_info, self.api, self.stack)
        self.stack.addWidget(result_widget)
        result_widget.load_result(self.task_id, result_data, show_export=False)
        self.stack.setCurrentWidget(result_widget)

    def start_polling(self):
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.load_messages)
        self.poll_timer.start(3000)

    def closeEvent(self, event):
        if self.poll_timer:
            self.poll_timer.stop()
        event.accept()