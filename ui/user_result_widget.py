import json
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTabWidget, QTextBrowser, QTableWidget, QTableWidgetItem,
                             QGroupBox, QPushButton, QMessageBox,
                             QComboBox, QTextEdit, QFileDialog, QGridLayout)
from PyQt6.QtCore import Qt

class UserResultWidget(QWidget):
    def __init__(self, user_info, api_client, stack):
        super().__init__()
        self.user_info = user_info
        self.api = api_client
        self.stack = stack
        self.current_task_id = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        self.title_label = QLabel("分析结果")
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self.title_label)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.export_btn = QPushButton("📄 导出报告")
        self.export_btn.clicked.connect(self.export_report)
        self.export_btn.setVisible(False)
        layout.addWidget(self.export_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.feedback_group = QGroupBox("您的反馈")
        feedback_layout = QVBoxLayout()

        grid_layout = QGridLayout()
        # 第一行：采纳类型
        self.type_label = QLabel("采纳类型:")
        grid_layout.addWidget(self.type_label, 0, 0)
        self.chosen_type_combo = QComboBox()
        self.chosen_type_combo.addItems(["采纳某个专家", "采纳综合建议", "不采纳"])
        self.chosen_type_combo.currentIndexChanged.connect(self.on_chosen_type_changed)
        grid_layout.addWidget(self.chosen_type_combo, 0, 1)
        # 第二行：选择专家
        self.agent_label = QLabel("选择专家:")
        self.agent_combo = QComboBox()
        grid_layout.addWidget(self.agent_label, 1, 0)
        grid_layout.addWidget(self.agent_combo, 1, 1)
        self.agent_label.setVisible(False)
        self.agent_combo.setVisible(False)
        feedback_layout.addLayout(grid_layout)

        feedback_layout.addWidget(QLabel("评论:"))
        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText("请输入您的评价或建议...")
        self.comment_edit.setMaximumHeight(80)
        feedback_layout.addWidget(self.comment_edit)

        self.submit_feedback_btn = QPushButton("提交反馈")
        self.submit_feedback_btn.clicked.connect(self.on_feedback)
        feedback_layout.addWidget(self.submit_feedback_btn)

        self.feedback_group.setLayout(feedback_layout)
        layout.addWidget(self.feedback_group)

        self.setLayout(layout)

    def load_result(self, task_id, result_data, show_export=False):
        self.current_task_id = task_id
        self._show_result_data(result_data)
        self.feedback_group.setVisible(True)
        self.submit_feedback_btn.setEnabled(True)
        self.export_btn.setVisible(show_export)
        self.comment_edit.clear()
        agents = result_data.get("agents", [])
        self.update_agent_list(agents)
        self.chosen_type_combo.setCurrentIndex(1)  # 默认“采纳综合建议”
        self.on_chosen_type_changed(1)

    def load_history_result(self, task_id, result_data, show_export=True):
        self.current_task_id = task_id
        self._show_result_data(result_data)
        self.feedback_group.setVisible(False)
        self.export_btn.setVisible(show_export)

    def _show_result_data(self, result_data):
        while self.tabs.count():
            self.tabs.removeTab(0)

        final_summary = result_data.get("final_summary", "")
        summary_widget = QTextBrowser()
        summary_widget.setMarkdown(final_summary)
        self.tabs.addTab(summary_widget, "综合建议")

        outputs = result_data.get("outputs", [])
        for out in outputs:
            agent_name = out.get("agent_name", "专家")
            output_text = out.get("output_text", "")
            text_widget = QTextBrowser()
            text_widget.setMarkdown(output_text)
            self.tabs.addTab(text_widget, agent_name)

        if outputs:
            matrix_widget = self.create_score_matrix_widget(outputs)
            self.tabs.addTab(matrix_widget, "评分矩阵")

        similarities = result_data.get("similarities", [])
        if similarities:
            agents = result_data.get("agents", [])
            agent_id_to_name = {a["id"]: a["agent_name"] for a in agents}
            sim_map_widget = self.create_similarity_widget(similarities, agent_id_to_name)
            self.tabs.addTab(sim_map_widget, "相似度热力图")

        conflicts = result_data.get("conflicts", [])
        if conflicts:
            conflicts_widget = self.create_conflicts_widget(conflicts)
            self.tabs.addTab(conflicts_widget, "冲突检测")

        if result_data.get("weighted_ranking"):
            ranking_widget = self.create_ranking_widget(result_data["weighted_ranking"])
            self.tabs.addTab(ranking_widget, "加权排名")

        if result_data.get("feedback"):
            feedback_widget = self.create_feedback_tab(result_data["feedback"])
            self.tabs.addTab(feedback_widget, "用户反馈")

    def create_score_matrix_widget(self, outputs):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        dimensions = ["benefit", "cost", "risk", "tech", "exec", "long_term"]
        dim_names = ["收益潜力", "成本可控性", "风险可控性", "技术可行性", "执行可行性", "长期价值"]
        table = QTableWidget()
        table.setRowCount(len(outputs))
        table.setColumnCount(len(dimensions))
        table.setHorizontalHeaderLabels(dim_names)
        table.setVerticalHeaderLabels([out["agent_name"] for out in outputs])

        for i, out in enumerate(outputs):
            score_dict = json.loads(out.get("score_json", "{}"))
            for j, dim in enumerate(dimensions):
                val = score_dict.get(dim, 0)
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, j, item)
        layout.addWidget(table)
        return widget

    def create_similarity_widget(self, similarities, agent_id_to_name):
        agent_ids = list(agent_id_to_name.keys())
        n = len(agent_ids)
        matrix = np.ones((n, n))
        id_to_idx = {aid: i for i, aid in enumerate(agent_ids)}
        for sim in similarities:
            i = id_to_idx.get(sim["agent_id_1"])
            j = id_to_idx.get(sim["agent_id_2"])
            if i is not None and j is not None:
                val = sim["similarity"]
                matrix[i][j] = val
                matrix[j][i] = val
        widget = QWidget()
        layout = QVBoxLayout(widget)
        fig, ax = plt.subplots(figsize=(6, 5))
        im = ax.imshow(matrix, cmap='coolwarm', vmin=0, vmax=1)
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels([agent_id_to_name[aid] for aid in agent_ids], rotation=45, ha='right')
        ax.set_yticklabels([agent_id_to_name[aid] for aid in agent_ids])
        plt.colorbar(im, ax=ax)
        ax.set_title("智能体观点相似度")
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        return widget

    def create_conflicts_widget(self, conflicts):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        if not conflicts:
            label = QLabel("未检测到明显冲突")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        else:
            browser = QTextBrowser()
            browser.setMinimumHeight(300)
            html_parts = []
            dim_map = {
                "benefit": "收益潜力", "cost": "成本可控性", "risk": "风险可控性",
                "tech": "技术可行性", "exec": "执行可行性", "long_term": "长期价值"
            }
            for conf in conflicts:
                dim = conf.get("dimension", "")
                level = conf.get("conflict_level", "low")
                explanation = conf.get("explanation", "")
                dim_cn = dim_map.get(dim, dim)
                html_parts.append(f"""
                <div style="border-bottom: 1px solid #ccc; margin-bottom: 10px; padding-bottom: 5px;">
                    <b>⚠️ 维度：{dim_cn}</b> (冲突等级：{level})<br>
                    <span style="color: #666;">{explanation}</span>
                </div>
                """)
            browser.setHtml("\n".join(html_parts))
            layout.addWidget(browser)
        return widget

    def create_ranking_widget(self, ranking):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        table = QTableWidget()
        table.setRowCount(len(ranking))
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["排名", "专家名称", "综合得分", "评分可用"])
        for row, item in enumerate(ranking):
            table.setItem(row, 0, QTableWidgetItem(str(item.get("rank", "-"))))
            table.setItem(row, 1, QTableWidgetItem(item["agent_name"]))
            table.setItem(row, 2, QTableWidgetItem(str(item["total_score"])))
            table.setItem(row, 3, QTableWidgetItem("是" if item["score_available"] else "否"))
        layout.addWidget(table)
        return widget

    def create_feedback_tab(self, feedback):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        browser = QTextBrowser()
        chosen_type = feedback.get("chosen_type", "none")
        chosen_agent_id = feedback.get("chosen_agent_id")
        comment = feedback.get("comment", "")
        submitted_at = feedback.get("submitted_at", "")
        if chosen_type == "agent":
            type_text = f"采纳专家 (ID: {chosen_agent_id})"
        elif chosen_type == "summary":
            type_text = "采纳综合建议"
        else:
            type_text = "不采纳"
        html = f"""
        <b>采纳类型：</b> {type_text}<br>
        <b>评论：</b> {comment}<br>
        <b>提交时间：</b> {submitted_at}
        """
        browser.setHtml(html)
        layout.addWidget(browser)
        return widget

    def update_agent_list(self, agents):
        self.agent_combo.clear()
        for agent in agents:
            self.agent_combo.addItem(agent.get("agent_name", "未知专家"), agent.get("id"))

    def on_chosen_type_changed(self, index):
        if index == 0:
            self.agent_label.setVisible(True)
            self.agent_combo.setVisible(True)
        else:
            self.agent_label.setVisible(False)
            self.agent_combo.setVisible(False)

    def on_feedback(self):
        if not self.current_task_id:
            QMessageBox.warning(self, "提示", "没有当前任务")
            return

        chosen_type_index = self.chosen_type_combo.currentIndex()
        if chosen_type_index == 0:
            chosen_type = "agent"
            chosen_agent_id = self.agent_combo.currentData()
            if chosen_agent_id is None:
                QMessageBox.warning(self, "错误", "请选择一个专家")
                return
        elif chosen_type_index == 1:
            chosen_type = "summary"
            chosen_agent_id = None
        else:
            chosen_type = "none"
            chosen_agent_id = None

        comment = self.comment_edit.toPlainText().strip()
        result = self.api.submit_feedback(
            task_id=self.current_task_id,
            chosen_type=chosen_type,
            chosen_agent_id=chosen_agent_id,
            comment=comment
        )
        if result and result.get("task_id"):
            QMessageBox.information(self, "反馈", "感谢您的反馈！")
            self.submit_feedback_btn.setEnabled(False)
        else:
            QMessageBox.warning(self, "错误", "提交反馈失败，请稍后重试")

    def export_report(self):
        if not self.current_task_id:
            QMessageBox.warning(self, "提示", "没有当前任务")
            return
        content = self.api.export_report(self.current_task_id)
        if content:
            file_path, _ = QFileDialog.getSaveFileName(self, "保存报告", "", "Markdown文件 (*.md)")
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                QMessageBox.information(self, "成功", "报告已导出")
        else:
            QMessageBox.warning(self, "错误", "导出失败，无法生成报告")