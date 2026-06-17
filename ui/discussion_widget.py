# ui/discussion_widget.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QScrollArea, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
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

        bubble.setMaximumWidth(900)
        bubble.setMinimumWidth(300)   # 可选，保证最小宽度


# ========== 后台获取结果的线程 ==========
class FetchResultThread(QThread):
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, api, task_id):
        super().__init__()
        self.api = api
        self.task_id = task_id

    def run(self):
        try:
            result = self.api.get_debate_result(self.task_id)
            if result:
                self.result_ready.emit(result)
            else:
                self.error.emit("获取结果失败")
        except Exception as e:
            self.error.emit(str(e))

# ========== 后台发送消息的线程 ==========
class SendMessageThread(QThread):
    finished = pyqtSignal(bool)  # 成功或失败
    error = pyqtSignal(str)

    def __init__(self, api, task_id, content, reply_scope):
        super().__init__()
        self.api = api
        self.task_id = task_id
        self.content = content
        self.reply_scope = reply_scope

    def run(self):
        try:
            success = self.api.send_message(self.task_id, self.content, self.reply_scope)
            self.finished.emit(success)
        except Exception as e:
            self.error.emit(str(e))

# ========== 正反方辩论的线程 ==========
class AgentExchangeThread(QThread):
    finished = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, api, task_id):
        super().__init__()
        self.api = api
        self.task_id = task_id

    def run(self):
        try:
            success = self.api.agent_exchange(self.task_id)
            self.finished.emit(success)
        except Exception as e:
            self.error.emit(str(e))

# ========== 初始消息发送线程 ==========
class InitialMessageThread(QThread):
    finished = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, api, task_id, decision_mode):
        super().__init__()
        self.api = api
        self.task_id = task_id
        self.decision_mode = decision_mode

    def run(self):
        try:
            reply_scope = "all_brief" if self.decision_mode != "debate" else "debate_round"
            success = self.api.send_message(
                self.task_id, "请各位专家对当前问题给出初步分析。", reply_scope
            )
            self.finished.emit(success)
        except Exception as e:
            self.error.emit(str(e))


class DiscussionWidget(QWidget):
    def __init__(self, user_info, api_client, stack, task_id, question, decision_mode):
        super().__init__()
        self.user_info = user_info
        self.api = api_client
        self.stack = stack
        self.task_id = task_id
        self.question = question
        self.decision_mode = decision_mode
        self.poll_timer = None          # 定时刷新消息
        self.status_timer = None        # 定时查询任务状态
        self._finalizing = False        # 防止重复提交 finalize
        self.fetch_thread = None        # 后台线程
        self._thinking_bubble = None    # 思考中气泡引用
        self._thinking_shown = False    # 是否已显示思考中

        self.init_ui()
        self._add_thinking_bubble("专家们正在思考您的问题...")
        self.start_polling()

        # 异步发送初始消息，不阻塞 UI
        self._send_initial_async()

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
        self.finalize_btn = QPushButton("生成报告")
        self.finalize_btn.clicked.connect(self.finalize)
        btn_layout.addWidget(self.exchange_btn)
        btn_layout.addWidget(self.finalize_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _send_initial_async(self):
        """异步发送初始消息，不阻塞 UI。"""
        messages = self.api.get_messages(self.task_id)
        has_user_or_agent = any(msg.get("role") in ("user", "agent") for msg in messages)
        if not has_user_or_agent:
            self.init_thread = InitialMessageThread(self.api, self.task_id, self.decision_mode)
            self.init_thread.finished.connect(self._on_initial_sent)
            self.init_thread.error.connect(lambda e: self._remove_thinking_bubble())
            self.init_thread.start()
        else:
            # 已有消息，直接加载
            self.load_messages()

    def _on_initial_sent(self, success):
        """初始消息发送完成，立即刷新。"""
        self._remove_thinking_bubble()
        if success:
            self.load_messages()
            # 重新加思考中，等待 AI 回复
            self._add_thinking_bubble("专家们正在分析...")

    # ── 思考中提示 ──────────────────────

    def _add_thinking_bubble(self, text="正在思考..."):
        """添加一个"思考中"的气泡。"""
        if self._thinking_shown:
            return
        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M")
        self._thinking_bubble = MessageBubble("agent", text, time_str, "思考中")
        self.chat_layout.addWidget(self._thinking_bubble)
        self._thinking_shown = True
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _remove_thinking_bubble(self):
        """移除思考中气泡。"""
        if self._thinking_bubble and self._thinking_shown:
            self.chat_layout.removeWidget(self._thinking_bubble)
            self._thinking_bubble.deleteLater()
            self._thinking_bubble = None
            self._thinking_shown = False

    def load_messages(self):
        messages = self.api.get_messages(self.task_id)
        self.display_messages(messages)

    # 删除旧的 auto_send_initial_message
    # def auto_send_initial_message(self): ...  (已用 _send_initial_async 替代)

    def display_messages(self, messages):
        # 增量更新：只追加新消息，避免销毁重建导致打字卡顿
        current_count = self.chat_layout.count()
        # 如果思考气泡在，算上它的偏移
        offset = 1 if self._thinking_shown else 0
        new_messages = messages[current_count - offset:] if current_count > offset else messages

        for msg in new_messages:
            role = msg.get("role", "")
            agent_name = msg.get("agent_name", "")
            content = msg.get("content", "")
            created_at = msg.get("created_at", "")
            time_str = created_at.split("T")[1][:5] if "T" in created_at else ""

            bubble = MessageBubble(role, content, time_str, agent_name)
            # 插入到思考气泡之前
            if self._thinking_shown and self._thinking_bubble:
                idx = self.chat_layout.indexOf(self._thinking_bubble)
                self.chat_layout.insertWidget(idx, bubble)
            else:
                self.chat_layout.addWidget(bubble)

        # 收到 Agent 回复时移除思考中
        has_agent = any(m.get("role") == "agent" for m in new_messages)
        if has_agent:
            self._remove_thinking_bubble()

        # 有新消息时滚动到底部
        if new_messages:
            QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ))

    def send_message(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        self.send_btn.setEnabled(False)
        self.send_btn.setText("发送中...")
        reply_scope = "all_brief" if self.decision_mode != "debate" else "debate_round"
        self.send_thread = SendMessageThread(self.api, self.task_id, text, reply_scope)
        self.send_thread.finished.connect(self.on_message_sent)
        self.send_thread.error.connect(self.on_message_error)
        self.send_thread.start()

    def on_message_sent(self, success):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")
        if success:
            self.input_edit.clear()
            self.load_messages()
            # 等待 AI 回复时显示思考中
            self._add_thinking_bubble("专家们正在回复...")
        else:
            QMessageBox.warning(self, "错误", "发送失败")

    def on_message_error(self, error_msg):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")
        QMessageBox.warning(self, "错误", f"发送失败: {error_msg}")

    def agent_exchange(self):
        self.exchange_btn.setEnabled(False)
        self.exchange_btn.setText("交锋中...")
        self.exchange_thread = AgentExchangeThread(self.api, self.task_id)
        self.exchange_thread.finished.connect(self.on_exchange_finished)
        self.exchange_thread.error.connect(self.on_exchange_error)
        self.exchange_thread.start()

    def on_exchange_finished(self, success):
        self.exchange_btn.setEnabled(True)
        self.exchange_btn.setText("辩手交锋")
        if success:
            self._add_thinking_bubble("辩手们正在交锋...")
            self.load_messages()
        else:
            QMessageBox.warning(self, "错误", "交锋失败，请重试")

    def on_exchange_error(self, error_msg):
        self.exchange_btn.setEnabled(True)
        self.exchange_btn.setText("辩手交锋")
        QMessageBox.warning(self, "错误", f"交锋失败: {error_msg}")
    # ========== 改进的 finalize 逻辑（防重复 + 轮询 + 后台获取） ==========
    def finalize(self):
        if self._finalizing:
            return
        self._finalizing = True
        self.finalize_btn.setEnabled(False)
        self.finalize_btn.setText("正在生成报告...")
        result = self.api.finalize_task(self.task_id)
        if result and result.get("status") in ("finalizing", "completed"):
            self.poll_task_status()
        else:
            QMessageBox.warning(self, "错误", "结束讨论失败，请重试")
            self._finalizing = False
            self.finalize_btn.setEnabled(True)
            self.finalize_btn.setText("生成报告")

    def poll_task_status(self):
        if self.status_timer:
            self.status_timer.stop()
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_status)
        self.status_timer.start(3000)   # 每3秒轮询一次

    def check_status(self):
        status = self.api.get_debate_status(self.task_id)
        if status == "completed":
            self.status_timer.stop()
            self.start_fetching_result()
        elif status == "failed":
            self.status_timer.stop()
            QMessageBox.warning(self, "错误", "报告生成失败")
            self._finalizing = False
            self.finalize_btn.setEnabled(True)
            self.finalize_btn.setText("生成报告")

    def start_fetching_result(self):
        """后台获取结果，避免界面卡死"""
        self.finalize_btn.setText("正在加载结果...")
        QApplication.processEvents()   # 刷新界面
        self.fetch_thread = FetchResultThread(self.api, self.task_id)
        self.fetch_thread.result_ready.connect(self.on_result_ready)
        self.fetch_thread.error.connect(self.on_result_error)
        self.fetch_thread.start()

    def on_result_ready(self, result_data):
        self.fetch_thread = None
        # 跳转到结果页
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

    def on_result_error(self, error_msg):
        self.fetch_thread = None
        QMessageBox.warning(self, "错误", f"加载结果失败: {error_msg}")
        self._finalizing = False
        self.finalize_btn.setEnabled(True)
        self.finalize_btn.setText("结束讨论")

    def start_polling(self):
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.load_messages)
        self.poll_timer.start(3000)

    def closeEvent(self, event):
        if self.poll_timer:
            self.poll_timer.stop()
        if self.status_timer:
            self.status_timer.stop()
        if hasattr(self, 'exchange_thread') and self.exchange_thread and self.exchange_thread.isRunning():
            self.exchange_thread.quit()
            self.exchange_thread.wait(1000)
        if hasattr(self, 'send_thread') and self.send_thread and self.send_thread.isRunning():
            self.send_thread.quit()
            self.send_thread.wait(1000)
        event.accept()