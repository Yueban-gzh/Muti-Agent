import csv
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QTableWidget,
                             QTableWidgetItem, QPushButton, QHBoxLayout, QLabel, QHeaderView,
                             QFileDialog, QMessageBox, QDialog, QFormLayout, QLineEdit, QTextEdit,
                             QComboBox, QDialogButtonBox, QTextBrowser)   # 注意添加了 QTextBrowser
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

class AdminWidget(QWidget):
    def __init__(self, user_info, api_client, stack):
        super().__init__()
        self.user_info = user_info
        self.api = api_client
        self.stack = stack
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        title = QLabel("管理员后台")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 任务管理标签页
        self.task_tab = QWidget()
        self.init_task_tab()
        self.tabs.addTab(self.task_tab, "用户与任务管理")

        # Agent模板管理标签页
        self.template_tab = QWidget()
        self.init_template_tab()
        self.tabs.addTab(self.template_tab, "Agent模板管理")

        # 反馈统计与系统日志
        self.stats_tab = QWidget()
        self.init_stats_tab()
        self.tabs.addTab(self.stats_tab, "反馈统计与系统日志")

        self.setLayout(layout)

    # ========== 任务管理 ==========
    def init_task_tab(self):
        layout = QVBoxLayout(self.task_tab)
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(6)
        self.task_table.setHorizontalHeaderLabels(["任务ID", "用户ID", "决策问题", "创建时间", "状态", "操作"])
        self.task_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.task_table)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_tasks)
        export_csv_btn = QPushButton("导出CSV")
        export_csv_btn.clicked.connect(self.export_csv)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(export_csv_btn)
        layout.addLayout(btn_layout)

        self.refresh_tasks()

    def refresh_tasks(self):
        tasks = self.api.get_all_tasks()
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.task_table.setItem(row, 0, QTableWidgetItem(str(task["task_id"])))
            self.task_table.setItem(row, 1, QTableWidgetItem(str(task["user_id"])))
            self.task_table.setItem(row, 2, QTableWidgetItem(task["question"]))
            self.task_table.setItem(row, 3, QTableWidgetItem(task["created_at"]))
            self.task_table.setItem(row, 4, QTableWidgetItem(task["status"]))

            btn = QPushButton("查看结果")
            btn.clicked.connect(lambda checked, t=task: self.view_task_result(t))
            self.task_table.setCellWidget(row, 5, btn)

    def view_task_result(self, task):
        result = self.api.get_debate_result(task["task_id"])
        if not result:
            QMessageBox.warning(self, "错误", "无法获取任务结果")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"任务 {task['task_id']} 详细结果")
        dialog.resize(1000, 700)
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget()

        # 综合建议
        summary_widget = QTextBrowser()
        summary_widget.setMarkdown(result.get("final_summary", ""))
        tabs.addTab(summary_widget, "综合建议")

        # 各专家分析
        for out in result.get("outputs", []):
            text_widget = QTextBrowser()
            text_widget.setMarkdown(out.get("output_text", ""))
            tabs.addTab(text_widget, out.get("agent_name", "专家"))

        # 评分矩阵
        if result.get("outputs"):
            matrix_widget = self._create_score_matrix_widget(result["outputs"])
            tabs.addTab(matrix_widget, "评分矩阵")

        # 相似度热力图
        if result.get("similarities"):
            heatmap_widget = self._create_similarity_widget(result["similarities"], result.get("agents", []))
            tabs.addTab(heatmap_widget, "相似度热力图")

        # 冲突检测
        if result.get("conflicts"):
            conflicts_widget = self._create_conflicts_widget(result["conflicts"])
            tabs.addTab(conflicts_widget, "冲突检测")

        # 用户反馈（如果存在）
        feedback = result.get("feedback")
        if feedback:
            feedback_widget = self._create_feedback_tab(feedback)
            tabs.addTab(feedback_widget, "用户反馈")

        layout.addWidget(tabs)
        dialog.exec()

    # 辅助方法：复用结果页的创建函数（简化版，也可直接调用 UserResultWidget 的内部方法）
    def _create_score_matrix_widget(self, outputs):
        import json
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
        widget = QWidget()
        layout = QVBoxLayout(widget)
        dims = ["benefit", "cost", "risk", "tech", "exec", "long_term"]
        dim_names = ["收益潜力", "成本可控性", "风险可控性", "技术可行性", "执行可行性", "长期价值"]
        table = QTableWidget()
        table.setRowCount(len(outputs))
        table.setColumnCount(len(dims))
        table.setHorizontalHeaderLabels(dim_names)
        table.setVerticalHeaderLabels([out["agent_name"] for out in outputs])
        for i, out in enumerate(outputs):
            scores = json.loads(out.get("score_json", "{}"))
            for j, d in enumerate(dims):
                val = scores.get(d, 0)
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, j, item)
        layout.addWidget(table)
        return widget

    def _create_similarity_widget(self, similarities, agents):
        import numpy as np
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from PyQt6.QtWidgets import QVBoxLayout, QWidget
        # 构建矩阵
        agent_id_to_name = {a["id"]: a["agent_name"] for a in agents}
        agent_ids = list(agent_id_to_name.keys())
        n = len(agent_ids)
        matrix = np.ones((n, n))
        idx_map = {aid: i for i, aid in enumerate(agent_ids)}
        for sim in similarities:
            i = idx_map.get(sim["agent_id_1"])
            j = idx_map.get(sim["agent_id_2"])
            if i is not None and j is not None:
                matrix[i][j] = sim["similarity"]
                matrix[j][i] = sim["similarity"]
        fig, ax = plt.subplots(figsize=(6, 5))
        im = ax.imshow(matrix, cmap='coolwarm', vmin=0, vmax=1)
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels([agent_id_to_name[aid] for aid in agent_ids], rotation=45, ha='right')
        ax.set_yticklabels([agent_id_to_name[aid] for aid in agent_ids])
        plt.colorbar(im, ax=ax)
        ax.set_title("智能体观点相似度")
        canvas = FigureCanvas(fig)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(canvas)
        return widget

    def _create_conflicts_widget(self, conflicts):
        from PyQt6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget
        widget = QWidget()
        layout = QVBoxLayout(widget)
        browser = QTextBrowser()
        html = "<ul>"
        for c in conflicts:
            html += f"<li><b>{c.get('dimension')}</b> (冲突等级 {c.get('conflict_level')})<br>{c.get('explanation')}</li>"
        html += "</ul>"
        browser.setHtml(html)
        layout.addWidget(browser)
        return widget

    def export_csv(self):
        tasks = self.api.get_all_tasks()
        if not tasks:
            QMessageBox.information(self, "提示", "没有任务可导出")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "保存CSV", "", "CSV文件 (*.csv)")
        if file_path:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["task_id", "user_id", "question", "created_at", "status"])
                writer.writeheader()
                writer.writerows(tasks)
            QMessageBox.information(self, "成功", f"已导出到 {file_path}")

    # ========== Agent模板管理 ==========
    def init_template_tab(self):
        layout = QVBoxLayout(self.template_tab)
        self.template_table = QTableWidget()
        self.template_table.setColumnCount(6)
        self.template_table.setHorizontalHeaderLabels(["ID", "名称", "角色描述", "关注领域", "风格", "操作"])
        self.template_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.template_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("新增模板")
        add_btn.clicked.connect(self.add_template)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_templates)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(refresh_btn)
        layout.addLayout(btn_layout)

        self.refresh_templates()

    def refresh_templates(self):
        templates = self.api.list_templates(include_inactive=True)
        self.template_table.setRowCount(len(templates))
        for row, t in enumerate(templates):
            self.template_table.setItem(row, 0, QTableWidgetItem(str(t["id"])))
            self.template_table.setItem(row, 1, QTableWidgetItem(t["name"]))
            self.template_table.setItem(row, 2, QTableWidgetItem(t["role_description"]))
            self.template_table.setItem(row, 3, QTableWidgetItem(t["focus_area"]))
            self.template_table.setItem(row, 4, QTableWidgetItem(t["tone"]))
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0,0,0,0)
            edit_btn = QPushButton("编辑")
            edit_btn.clicked.connect(lambda checked, tid=t["id"]: self.edit_template(tid))
            del_btn = QPushButton("删除")
            del_btn.clicked.connect(lambda checked, tid=t["id"]: self.delete_template(tid))
            btn_layout.addWidget(edit_btn)
            btn_layout.addWidget(del_btn)
            self.template_table.setCellWidget(row, 5, btn_widget)

    def add_template(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("新增模板")
        layout = QFormLayout(dialog)
        name_edit = QLineEdit()
        role_edit = QLineEdit()
        focus_edit = QLineEdit()
        tone_edit = QComboBox()
        tone_edit.addItems(["严谨型", "鼓励型", "中立型", "激进型", "保守型"])
        active_cb = QComboBox()
        active_cb.addItems(["启用", "禁用"])
        layout.addRow("名称:", name_edit)
        layout.addRow("角色描述:", role_edit)
        layout.addRow("关注领域:", focus_edit)
        layout.addRow("风格:", tone_edit)
        layout.addRow("状态:", active_cb)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            data = {
                "name": name_edit.text(),
                "role_description": role_edit.text(),
                "focus_area": focus_edit.text(),
                "tone": tone_edit.currentText(),
                "is_active": 1 if active_cb.currentText() == "启用" else 0
            }
            if data["name"]:
                self.api.create_template(data)
                self.refresh_templates()
                QMessageBox.information(self, "成功", "模板已创建")

    def edit_template(self, template_id):
        templates = self.api.list_templates(include_inactive=True)
        tmpl = next((t for t in templates if t["id"] == template_id), None)
        if not tmpl:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑模板 - {tmpl['name']}")
        layout = QFormLayout(dialog)
        name_edit = QLineEdit(tmpl["name"])
        role_edit = QLineEdit(tmpl["role_description"])
        focus_edit = QLineEdit(tmpl["focus_area"])
        tone_edit = QComboBox()
        tone_edit.addItems(["严谨型", "鼓励型", "中立型", "激进型", "保守型"])
        tone_edit.setCurrentText(tmpl["tone"])
        active_cb = QComboBox()
        active_cb.addItems(["启用", "禁用"])
        active_cb.setCurrentIndex(0 if tmpl["is_active"] else 1)
        layout.addRow("名称:", name_edit)
        layout.addRow("角色描述:", role_edit)
        layout.addRow("关注领域:", focus_edit)
        layout.addRow("风格:", tone_edit)
        layout.addRow("状态:", active_cb)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            data = {
                "name": name_edit.text(),
                "role_description": role_edit.text(),
                "focus_area": focus_edit.text(),
                "tone": tone_edit.currentText(),
                "is_active": 1 if active_cb.currentText() == "启用" else 0
            }
            self.api.update_template(template_id, data)
            self.refresh_templates()
            QMessageBox.information(self, "成功", "模板已更新")

    def delete_template(self, template_id):
        confirm = QMessageBox.question(self, "确认删除", "确定要删除此模板吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            success = self.api.delete_template(template_id)
            if success:
                self.refresh_templates()
                QMessageBox.information(self, "成功", "模板已删除")
            else:
                QMessageBox.warning(self, "错误", "删除失败")

    # ========== 反馈统计与系统日志 ==========
    def init_stats_tab(self):
        layout = QVBoxLayout(self.stats_tab)
        # 统计信息卡片
        stats_frame = QWidget()
        stats_layout = QHBoxLayout(stats_frame)
        self.stats_labels = {}
        for key in ["total_users", "total_tasks", "completed_tasks", "feedback_count", "active_templates"]:
            label = QLabel()
            label.setStyleSheet("border: 1px solid #ccc; padding: 8px; border-radius: 5px;")
            stats_layout.addWidget(label)
            self.stats_labels[key] = label
        layout.addWidget(stats_frame)

        # 日志表格
        layout.addWidget(QLabel("操作日志"))
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(4)
        self.log_table.setHorizontalHeaderLabels(["ID", "用户ID", "事件类型", "描述", "时间"])
        self.log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.log_table)

        refresh_btn = QPushButton("刷新统计与日志")
        refresh_btn.clicked.connect(self.refresh_stats)
        layout.addWidget(refresh_btn)

        self.refresh_stats()

    def refresh_stats(self):
        stats = self.api.get_admin_stats()
        self.stats_labels["total_users"].setText(f"用户总数: {stats.get('total_users', 0)}")
        self.stats_labels["total_tasks"].setText(f"任务总数: {stats.get('total_tasks', 0)}")
        self.stats_labels["completed_tasks"].setText(f"已完成: {stats.get('completed_tasks', 0)}")
        self.stats_labels["feedback_count"].setText(f"反馈数: {stats.get('feedback_count', 0)}")
        self.stats_labels["active_templates"].setText(f"启用模板: {stats.get('active_templates', 0)}")

        logs = self.api.get_logs()
        self.log_table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            self.log_table.setItem(row, 0, QTableWidgetItem(str(log["id"])))
            self.log_table.setItem(row, 1, QTableWidgetItem(str(log["user_id"])))
            self.log_table.setItem(row, 2, QTableWidgetItem(log["event_type"]))
            self.log_table.setItem(row, 3, QTableWidgetItem(log["description"]))
            self.log_table.setItem(row, 4, QTableWidgetItem(log["created_at"]))
    def _create_feedback_tab(self, feedback):
        from PyQt6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget
        widget = QWidget()
        layout = QVBoxLayout(widget)
        browser = QTextBrowser()
        adopted = "采纳" if feedback.get("chosen_type") == "summary" else "不采纳"
        comment = feedback.get("comment", "")
        submitted_at = feedback.get("submitted_at", "")
        html = f"""
        <b>采纳情况：</b> {adopted}<br>
        <b>评论：</b> {comment}<br>
        <b>提交时间：</b> {submitted_at}
        """
        browser.setHtml(html)
        layout.addWidget(browser)
        return widget