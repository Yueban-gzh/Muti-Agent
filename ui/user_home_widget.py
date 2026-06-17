from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTextEdit, QSpinBox, QPushButton, QGroupBox,
                             QFormLayout, QLineEdit, QDoubleSpinBox, QScrollArea,
                             QMessageBox, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import QThread, pyqtSignal
from ui.config import USE_REAL_API

class StartDebateThread(QThread):
    finished = pyqtSignal(object)  # 返回创建结果字典
    error = pyqtSignal(str)

    def __init__(self, api, payload):
        super().__init__()
        self.api = api
        self.payload = payload

    def run(self):
        try:
            result = self.api.start_debate(self.payload)
            if result:
                self.finished.emit(result)
            else:
                self.error.emit("创建任务失败")
        except Exception as e:
            self.error.emit(str(e))
class RefreshStatsThread(QThread):
    finished = pyqtSignal(dict, list)  # (stats, logs)
    error = pyqtSignal(str)

    def __init__(self, api, event_type):
        super().__init__()
        self.api = api
        self.event_type = event_type

    def run(self):
        try:
            stats = self.api.get_admin_stats()
            logs = self.api.get_admin_logs(event_type=self.event_type, limit=100)
            self.finished.emit(stats, logs)
        except Exception as e:
            self.error.emit(str(e))

MODE_MAP = {
    "多角度分析": "multi_angle",
    "正反辩论": "debate",
    "专家会诊": "expert_consult",
    "风险评审": "risk_review",
}


class UserHomeWidget(QWidget):
    def __init__(self, user_info, api_client, stack, result_widget):
        super().__init__()
        self.user_info = user_info
        self.api = api_client
        self.stack = stack
        self.result_widget = result_widget
        self.init_ui()
        self.reset_form()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("创建新的决策任务")
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        # 决策问题
        self.question_edit = QTextEdit()
        self.question_edit.setPlaceholderText("请输入您的决策问题，例如：我是否应该考研？")
        self.question_edit.setMaximumHeight(100)
        layout.addWidget(QLabel("决策问题:"))
        layout.addWidget(self.question_edit)

        # 决策模式
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("决策模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["多角度分析", "正反辩论", "专家会诊", "风险评审"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.mode_combo.setCurrentIndex(0)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # Agent 数量
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("智能体数量:"))
        self.agent_spin = QSpinBox()
        self.agent_spin.setRange(2, 5)
        self.agent_spin.setValue(2)
        self.agent_spin.valueChanged.connect(self.on_agent_count_changed)
        count_layout.addWidget(self.agent_spin)
        count_layout.addStretch()
        layout.addLayout(count_layout)

        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.agent_container = QWidget()
        self.agent_layout = QVBoxLayout(self.agent_container)
        self.scroll_area.setWidget(self.agent_container)
        layout.addWidget(self.scroll_area)

        self.submit_btn = QPushButton("开始分析")
        self.submit_btn.clicked.connect(self.on_submit)
        layout.addWidget(self.submit_btn)

        self.setLayout(layout)
        self.on_agent_count_changed(2)
    
    def on_mode_changed(self, mode_text):
        is_debate = (mode_text == "正反辩论")
        for inp in self.agent_inputs:
            label = inp.get("stance_label")
            combo = inp.get("stance_combo")
            if label:
                label.setVisible(is_debate)
            if combo:
                combo.setVisible(is_debate)

    def on_agent_count_changed(self, count):
        # 清空
        for i in reversed(range(self.agent_layout.count())):
            widget = self.agent_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        self.agent_inputs = []
        for i in range(count):
            group = QGroupBox(f"智能体 {i+1}")
            form = QFormLayout()
            name_edit = QLineEdit()
            name_edit.setPlaceholderText("例如：木·生长型")
            
            role_edit = QLineEdit()
            role_edit.setPlaceholderText("角色/专业背景，如：产品创新专家")
            
            focus_edit = QLineEdit()
            focus_edit.setPlaceholderText("关注领域，如：增长机会、长期价值")
            
            tone_edit = QLineEdit()
            tone_edit.setPlaceholderText("输出风格，如：鼓励型/严谨型/中立型")
            # 在 tone_edit 后面添加
            stance_combo = QComboBox()
            stance_items = {
                "正方": "pro",
                "反方": "con",
                "中立": "neutral",
                "评审": "judge"
            }
            for display, value in stance_items.items():
                stance_combo.addItem(display, value)
            stance_combo.setCurrentIndex(2)  # 默认选中“中立”
            stance_label = QLabel("辩论立场:")
            weight_spin = QDoubleSpinBox()
            weight_spin.setRange(0.0, 1.0)
            weight_spin.setSingleStep(0.05)
            weight_spin.setValue(0.5)

            form.addRow("名称:", name_edit)
            form.addRow(stance_label, stance_combo)
            form.addRow("角色描述:", role_edit)
            form.addRow("关注领域:", focus_edit)
            form.addRow("风格:", tone_edit)
             
            form.addRow("权重:", weight_spin)
            group.setLayout(form)
            self.agent_layout.addWidget(group)
            self.agent_inputs.append({
                "agent": name_edit,
                "role": role_edit,
                "focus": focus_edit,
                "tone": tone_edit,
                "weight": weight_spin,
                "stance_combo": stance_combo,
                "stance_label": stance_label
            })
        self.on_mode_changed(self.mode_combo.currentText())

    def on_submit(self):
        if hasattr(self, '_submitting') and self._submitting:
            return
        question = self.question_edit.toPlainText().strip()
        if not question:
            QMessageBox.warning(self, "错误", "请输入决策问题")
            return

        decision_mode = MODE_MAP[self.mode_combo.currentText()]

        agents = []
        for idx, inp in enumerate(self.agent_inputs):
            name = inp["agent"].text().strip()
            role = inp["role"].text().strip()
            focus = inp["focus"].text().strip()
            tone = inp["tone"].text().strip()
            if not name:
                QMessageBox.warning(self, "错误", f"智能体 {idx+1} 的名称不能为空")
                return
            agent = {
                "agent_name": name,
                "role_description": role,
                "focus_area": focus,
                "tone": tone,
            }
            if decision_mode == "debate":
                stance = inp["stance_combo"].currentData()
                agent["stance"] = stance
            agents.append(agent)

        payload = {
            "question": question,
            "decision_mode": decision_mode,
            "agent_count": len(agents),
            "agents": agents
        }

        # 禁用按钮，显示创建中
        self.submit_btn.setEnabled(False)
        self.submit_btn.setText("创建中...")
        self._submitting = True

        # 启动异步线程
        self.debate_thread = StartDebateThread(self.api, payload)
        self.debate_thread.finished.connect(self.on_debate_created)
        self.debate_thread.error.connect(self.on_debate_error)
        self.debate_thread.start()

    def on_debate_created(self, result):
        self._reset_submit_button()
        if result and result.get("task_id"):
            task_id = result["task_id"]
            from ui.discussion_widget import DiscussionWidget
            discussion_widget = DiscussionWidget(
                self.user_info, self.api, self.stack,
                task_id, self.question_edit.toPlainText().strip(),
                MODE_MAP[self.mode_combo.currentText()]
            )
            self.stack.addWidget(discussion_widget)
            self.stack.setCurrentWidget(discussion_widget)
        else:
            QMessageBox.warning(self, "错误", "创建任务失败")

    def on_debate_error(self, error_msg):
        self._reset_submit_button()
        QMessageBox.warning(self, "错误", f"创建任务失败: {error_msg}")

    def _reset_submit_button(self):
        self.submit_btn.setEnabled(True)
        self.submit_btn.setText("开始分析")
        if hasattr(self, '_submitting'):
            self._submitting = False

    def poll_task_result(self, task_id):
        """开始轮询任务状态，每2秒检查一次，不设超时"""
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(lambda: self.check_task_status(task_id))
        self.poll_timer.start(2000)

    def check_task_status(self, task_id):
        status = self.api.get_debate_status(task_id)
        if status is None:
            # 请求超时，继续等待（不停止定时器）
            return
        if status == "completed":
            self.poll_timer.stop()
            final_result = self.api.get_debate_result(task_id)
            if final_result:
                self.result_widget.load_result(task_id, final_result)
                self.stack.setCurrentWidget(self.result_widget)
            else:
                QMessageBox.warning(self, "错误", "获取任务结果失败")
            self._reset_submit_button()
        elif status == "failed":
            self.poll_timer.stop()
            QMessageBox.warning(self, "错误", "任务分析失败")
            self._reset_submit_button()
        # 其他状态（pending/processing）继续轮询，永不超时

    def _reset_submit_button(self):
        """恢复按钮状态"""
        self.submit_btn.setEnabled(True)
        self.submit_btn.setText("开始分析")
        self._submitting = False
        if hasattr(self, 'loading_label'):
            self.loading_label.setVisible(False)
    def showEvent(self, event):
        self.reset_form()
        super().showEvent(event)

    def reset_form(self):
        self.question_edit.clear()
        self.mode_combo.setCurrentIndex(0)
        self.agent_spin.setValue(2)
        self.on_agent_count_changed(2)