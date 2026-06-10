import csv
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QTableWidget,
                             QTableWidgetItem, QPushButton, QHBoxLayout, QLabel, QHeaderView,
                             QFileDialog, QMessageBox, QDialog, QFormLayout, QLineEdit, QTextEdit,
                             QComboBox, QDialogButtonBox, QTextBrowser, QSizePolicy, QGridLayout,
                             QScrollArea, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# ========== 异步刷新线程 ==========
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

# ========== 主管理员窗口 ==========
class AdminWidget(QWidget):
    def __init__(self, user_info, api_client, stack):
        super().__init__()
        self.user_info = user_info
        self.api = api_client
        self.stack = stack
        
        self.setStyleSheet("""
            QWidget#StatCard {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QTableWidget QPushButton {
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton[type="danger"] {
                background-color: #334155;
                color: #f87171; 
                border: 1px solid #475569;
            }
            QPushButton[type="danger"]:hover {
                background-color: #ef4444;
                color: #ffffff;
                border-color: #f87171;
            }
        """)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        title_layout = QHBoxLayout()
        title = QLabel("管理员后台")
        title.setObjectName("welcome_label")
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        logout_btn = QPushButton("退出登录")
        logout_btn.setProperty("type", "danger")
        logout_btn.clicked.connect(self.logout)
        title_layout.addWidget(logout_btn)
        
        layout.addLayout(title_layout)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 任务管理标签页
        self.task_tab = QWidget()
        self.init_task_tab()
        self.tabs.addTab(self.task_tab, "用户与任务管理")

        # 用户管理标签页
        self.user_tab = QWidget()
        self.init_user_tab()
        self.tabs.addTab(self.user_tab, "用户管理")

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
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(16)
        
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(6)
        self.task_table.setHorizontalHeaderLabels(["任务ID", "用户ID", "决策问题", "创建时间", "状态", "操作"])
        self.task_table.setAlternatingRowColors(True)
        self.task_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.task_table.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.task_table)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_tasks)
        export_csv_btn = QPushButton("导出CSV")
        export_csv_btn.clicked.connect(self.export_csv)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(export_csv_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.refresh_tasks()

    def refresh_tasks(self):
        tasks = self.api.get_all_tasks()
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.task_table.setItem(row, 0, self._create_center_item(str(task["id"])))
            self.task_table.setItem(row, 1, self._create_center_item(str(task["user_id"])))
            self.task_table.setItem(row, 2, self._create_center_item(task["question"]))
            self.task_table.setItem(row, 3, self._create_center_item(task["created_at"]))

            status = task.get("status", "")
            status_item = self._create_center_item(status)
            if status == "completed":
                status_item.setForeground(Qt.GlobalColor.green)
            elif status in ("discussing", "finalizing"):
                status_item.setForeground(Qt.GlobalColor.cyan)
            elif status == "failed":
                status_item.setForeground(Qt.GlobalColor.red)
            self.task_table.setItem(row, 4, status_item)

            # 操作列
            widget = QWidget()
            btn_layout = QHBoxLayout(widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            if status == "completed":
                view_btn = QPushButton("查看结果")
                view_btn.setStyleSheet("""
                QPushButton {
                    font-size: 12px;
                    font-weight: bold;
                    color: #0f172a;
                    background-color: #94a3b8;
                    border: 1px solid #94a3b8;
                    border-radius: 5px;
                    padding: 4px 8px;
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
                view_btn.setMinimumWidth(80)
                view_btn.setMinimumHeight(25)    
                view_btn.clicked.connect(lambda checked, t=task: self.view_task_result(t))
                btn_layout.addWidget(view_btn)
            elif status in ("discussing", "finalizing"):
                discuss_btn = QPushButton("进入讨论室")
                discuss_btn.clicked.connect(lambda checked, t=task: self.open_discussion(t))
                btn_layout.addWidget(discuss_btn)
            else:
                info_btn = QPushButton("无操作")
                info_btn.setEnabled(False)
                btn_layout.addWidget(info_btn)
            btn_layout.addStretch()
            self.task_table.setCellWidget(row, 5, widget)

    def _create_center_item(self, text):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item
    
    def open_discussion(self, task):
        """管理员打开讨论室"""
        from ui.discussion_widget import DiscussionWidget
        for i in range(self.stack.count()):
            w = self.stack.widget(i)
            if isinstance(w, DiscussionWidget) and hasattr(w, 'task_id') and w.task_id == task["id"]:
                self.stack.setCurrentWidget(w)
                return
        discussion = DiscussionWidget(
            self.user_info, self.api, self.stack,
            task["id"], task["question"], task.get("decision_mode", "multi_angle")
        )
        self.stack.addWidget(discussion)
        self.stack.setCurrentWidget(discussion)

    # ========== 查看任务结果（弹窗） ==========
    def view_task_result(self, task):
        result = self.api.get_debate_result(task["id"])
        if not result:
            QMessageBox.warning(self, "错误", "无法获取任务结果")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"任务 {task['id']} 详细结果")
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
        outputs = result.get("outputs", [])
        if outputs:
            matrix_widget = self._create_score_matrix_widget(outputs)
            tabs.addTab(matrix_widget, "评分矩阵")
        
        # 相似度热力图
        similarities = result.get("similarities", [])
        if similarities:
            agents = result.get("agents", [])
            agent_id_to_name = {a["id"]: a["agent_name"] for a in agents}
            heatmap_widget = self._create_similarity_widget(similarities, agent_id_to_name)
            tabs.addTab(heatmap_widget, "相似度热力图")
        
        # 冲突检测
        conflicts = result.get("conflicts", [])
        if conflicts:
            conflicts_widget = self._create_conflicts_widget(conflicts)
            tabs.addTab(conflicts_widget, "冲突检测")
        
        # 加权排名
        ranking = result.get("weighted_ranking")
        if ranking:
            ranking_widget = self._create_ranking_widget(ranking)
            tabs.addTab(ranking_widget, "加权排名")
        
        layout.addWidget(tabs)
        dialog.exec()

    # ---------- 辅助展示方法 ----------
    def _create_score_matrix_widget(self, outputs):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        dimensions = ["benefit", "cost", "risk", "tech", "exec", "long_term"]
        dim_names = ["收益潜力", "成本可控性", "风险可控性", "技术可行性", "执行可行性", "长期价值"]
        table = QTableWidget()
        table.setRowCount(len(outputs))
        table.setColumnCount(len(dimensions))
        table.setHorizontalHeaderLabels(dim_names)
        table.setVerticalHeaderLabels([out["agent_name"] for out in outputs])
        table.setAlternatingRowColors(True)
        for i, out in enumerate(outputs):
            try:
                score_dict = json.loads(out.get("score_json", "{}"))
            except:
                score_dict = {}
            for j, dim in enumerate(dimensions):
                val = score_dict.get(dim, 0)
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, j, item)
        layout.addWidget(table)
        return widget

    def _create_similarity_widget(self, similarities, agent_id_to_name):
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

    def _create_conflicts_widget(self, conflicts):
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

    def _create_ranking_widget(self, ranking):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        table = QTableWidget()
        table.setRowCount(len(ranking))
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["排名", "专家名称", "综合得分", "评分可用"])
        table.setAlternatingRowColors(True)
        for row, item in enumerate(ranking):
            table.setItem(row, 0, self._create_center_item(str(item.get("rank", "-"))))
            table.setItem(row, 1, QTableWidgetItem(item["agent_name"]))
            table.setItem(row, 2, self._create_center_item(str(item["total_score"])))
            table.setItem(row, 3, self._create_center_item("是" if item.get("score_available") else "否"))
        layout.addWidget(table)
        return widget

    # ========== 导出 CSV ==========
    def export_csv(self):
        tasks = self.api.get_all_tasks()
        if not tasks:
            QMessageBox.information(self, "提示", "没有任务可导出")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "保存CSV", "", "CSV文件 (*.csv)")
        if file_path:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["id", "user_id", "question", "created_at", "status"])
                writer.writeheader()
                writer.writerows(tasks)
            QMessageBox.information(self, "成功", f"已导出到 {file_path}")

    # ========== 用户管理 ==========
    def init_user_tab(self):
        layout = QVBoxLayout(self.user_tab)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(16)

        self.user_table = QTableWidget()
        self.user_table.setColumnCount(4)
        self.user_table.setHorizontalHeaderLabels(["用户ID", "用户名", "角色", "注册时间"])
        self.user_table.setAlternatingRowColors(True)
        self.user_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.user_table)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新用户列表")
        refresh_btn.clicked.connect(self.refresh_users)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.refresh_users()

    def refresh_users(self):
        users = self.api.get_all_users()
        self.user_table.setRowCount(len(users))
        for row, user in enumerate(users):
            self.user_table.setItem(row, 0, self._create_center_item(str(user["id"])))
            self.user_table.setItem(row, 1, QTableWidgetItem(user["username"]))
            self.user_table.setItem(row, 2, self._create_center_item(user["role"]))
            self.user_table.setItem(row, 3, self._create_center_item(user["created_at"]))

    # ========== Agent模板管理 ==========
    def init_template_tab(self):
        layout = QVBoxLayout(self.template_tab)
        layout.setContentsMargins(16, 20, 16, 16)
        
        self.template_table = QTableWidget()
        self.template_table.setColumnCount(6)
        self.template_table.setHorizontalHeaderLabels(["ID", "名称", "角色描述", "关注领域", "风格", "操作"])
        self.template_table.setAlternatingRowColors(True)
        
        header = self.template_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.template_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("新增模板")
        add_btn.clicked.connect(self.add_template)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_templates)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.refresh_templates()

    def refresh_templates(self):
        response = self.api.list_templates(include_inactive=True)
        if isinstance(response, dict):
            templates = response.get("templates", [])
        else:
            templates = response if isinstance(response, list) else []
        
        self.template_table.setRowCount(len(templates))
        for row, t in enumerate(templates):
            if not isinstance(t, dict):
                continue
            self.template_table.setRowHeight(row, 44)
            self.template_table.setItem(row, 0, self._create_center_item(str(t.get("id", ""))))
            
            name_item = QTableWidgetItem(t.get("name", ""))
            font = self.font()
            font.setBold(True)
            name_item.setFont(font)
            self.template_table.setItem(row, 1, name_item)
            
            self.template_table.setItem(row, 2, QTableWidgetItem(t.get("role_description", "")))
            self.template_table.setItem(row, 3, QTableWidgetItem(t.get("focus_area", "")))
            self.template_table.setItem(row, 4, self._create_center_item(t.get("tone", "")))
            
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(6, 0, 6, 0)
            btn_layout.setSpacing(6)
            
            edit_btn = QPushButton("编辑")
            edit_btn.clicked.connect(lambda checked, tid=t["id"]: self.edit_template(tid))
            
            del_btn = QPushButton("删除")
            del_btn.setProperty("type", "danger")
            del_btn.clicked.connect(lambda checked, tid=t["id"]: self.delete_template(tid))
            
            btn_style = "QPushButton { padding: 4px 12px; font-size: 13px; }"
            edit_btn.setStyleSheet(btn_style)
            del_btn.setStyleSheet(btn_style)
            
            btn_layout.addWidget(edit_btn)
            btn_layout.addWidget(del_btn)
            self.template_table.setCellWidget(row, 5, btn_widget)

    def add_template(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("新增模板")
        layout = QFormLayout(dialog)
        layout.setVerticalSpacing(12)
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
        response = self.api.list_templates(include_inactive=True)
        if isinstance(response, dict):
            templates = response.get("templates", [])
        else:
            templates = response if isinstance(response, list) else []
        
        tmpl = next((t for t in templates if t["id"] == template_id), None)
        if not tmpl:
            QMessageBox.warning(self, "错误", "模板不存在")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑模板 - {tmpl['name']}")
        layout = QFormLayout(dialog)
        layout.setVerticalSpacing(12)
        name_edit = QLineEdit(tmpl["name"])
        role_edit = QLineEdit(tmpl.get("role_description", ""))
        focus_edit = QLineEdit(tmpl.get("focus_area", ""))
        tone_edit = QComboBox()
        tone_edit.addItems(["严谨型", "鼓励型", "中立型", "激进型", "保守型"])
        tone_edit.setCurrentText(tmpl.get("tone", "中立型"))
        active_cb = QComboBox()
        active_cb.addItems(["启用", "禁用"])
        active_cb.setCurrentIndex(0 if tmpl.get("is_active", 1) else 1)
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
        response = self.api.list_templates(include_inactive=True)
        if isinstance(response, dict):
            templates = response.get("templates", [])
        else:
            templates = response if isinstance(response, list) else []
        tmpl = next((t for t in templates if t["id"] == template_id), None)
        if not tmpl:
            QMessageBox.warning(self, "错误", "模板不存在")
            return
        confirm = QMessageBox.question(self, "确认删除", f"确定要删除模板「{tmpl['name']}」吗？", 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            success = self.api.delete_template(template_id)
            if success:
                self.refresh_templates()
                QMessageBox.information(self, "成功", "模板已删除")
            else:
                QMessageBox.warning(self, "错误", "删除失败")

    # ========== 反馈统计与系统日志（异步版） ==========
    def init_stats_tab(self):
        # 1. 最外层的主布局（垂直排列：上方是滚动区域，下方是固定刷新按钮）
        main_layout = QVBoxLayout(self.stats_tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # 2. 创建滚动区域（只包裹卡片和日志面板）
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        main_layout.addWidget(scroll_area)

        # 滚动区域内部的承载容器
        container_widget = QWidget()
        scroll_area.setWidget(container_widget)

        # 内部容器的布局
        layout = QVBoxLayout(container_widget)
        layout.setContentsMargins(24, 24, 24, 12)
        layout.setSpacing(24)

        # --- [统计卡片区域] ---
        stats_frame = QWidget()
        stats_layout = QGridLayout(stats_frame)
        stats_layout.setSpacing(12)
        stats_layout.setContentsMargins(0, 0, 0, 0)

        card_configs = [
            ("total_users", "用户总数", "#94a3b8", 0, 0),
            ("total_tasks", "任务总数", "#b89a6a", 0, 1),
            ("completed_tasks", "已完成任务", "#22c55e", 0, 2),
            ("failed_tasks", "失败任务", "#ef4444", 1, 0),
            ("total_feedback", "总反馈数", "#fbbf24", 1, 1),
            ("active_templates", "启用模板", "#fbbf24", 1, 2),
            ("task_queue_depth", "队列深度", "#60a5fa", 2, 0),
            ("pipeline_active", "活动流水线", "#60a5fa", 2, 1),
            ("llm_active", "LLM活跃数", "#60a5fa", 2, 2),
        ]

        self.stats_labels = {}
        for key, label_name, border_color, row, col in card_configs:
            card = QWidget()
            card.setObjectName("StatCard")
            card.setStyleSheet(f"""
                QWidget#StatCard {{ 
                    border-left: 4px solid {border_color}; 
                    border-top: 1px solid transparent;
                    border-right: 1px solid transparent;
                    border-bottom: 1px solid transparent;
                    border-radius: 6px; 
                }}
                QWidget#StatCard:hover {{
                    border-top: 1px solid {border_color}40;
                    border-right: 1px solid {border_color}40;
                    border-bottom: 1px solid {border_color}40;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)
            
            title_lbl = QLabel(label_name)
            title_lbl.setStyleSheet("font-size: 12px; font-weight: 500;") 
            
            value_lbl = QLabel("0")
            value_lbl.setStyleSheet(f"color: {border_color}; font-size: 22px; font-weight: 700;") 
            
            card_layout.addWidget(title_lbl)
            card_layout.addWidget(value_lbl)
            stats_layout.addWidget(card, row, col)
            self.stats_labels[key] = value_lbl

        layout.addWidget(stats_frame)

        # --- [下方一体化控制与列表面板] ---
        panel_widget = QWidget()
        panel_widget.setObjectName("LogPanel")
        panel_widget.setStyleSheet("QWidget#LogPanel { border: 1px solid rgba(128, 128, 128, 0.15); border-radius: 12px; }")
        
        panel_layout = QVBoxLayout(panel_widget)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(16)

        # 筛选栏
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)
        
        filter_title = QLabel("事件类型:")
        filter_title.setStyleSheet("font-size: 14px; font-weight: bold; border: none; background: transparent;")
        filter_layout.addWidget(filter_title)
        
        self.event_type_combo = QComboBox()
        self.event_type_combo.setMinimumWidth(140)
        
        event_type_map = {
            "全部": None,
            "用户注册": "user.register",
            "用户登录": "user.login",
            "创建任务": "task.create",
            "任务开始分析": "task.processing",
            "任务完成": "task.completed",
            "任务失败": "task.failed",
            "提交反馈": "feedback.vote"
        }
        for display, _ in event_type_map.items():
            self.event_type_combo.addItem(display)
        filter_layout.addWidget(self.event_type_combo)
        
        self.filter_btn = QPushButton("筛选")
        self.filter_btn.clicked.connect(self._start_refresh)   # 异步刷新
        filter_layout.addWidget(self.filter_btn)
        filter_layout.addStretch()
        
        panel_layout.addLayout(filter_layout)

        # 日志表格标题
        log_title = QLabel("操作日志明细")
        log_title.setStyleSheet("font-size: 15px; font-weight: bold; border: none; background: transparent; margin-top: 8px;")
        panel_layout.addWidget(log_title)

        # 日志表格
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(5)
        self.log_table.setHorizontalHeaderLabels(["ID", "用户ID", "事件类型", "描述", "时间"])
        self.log_table.setAlternatingRowColors(True)
        self.log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.log_table.setMinimumHeight(450)
        
        self.log_table.setStyleSheet("""
            QTableWidget { border: none; border-radius: 0px; }
            QTableWidget::item { padding: 10px; }
            QHeaderView::section { padding: 8px; border: none; font-weight: 600; }
        """)
        self.log_table.setFrameShape(QFrame.Shape.NoFrame)
        self.log_table.verticalHeader().setVisible(False)
        panel_layout.addWidget(self.log_table)
        
        layout.addWidget(panel_widget)

        # --- 固定在最底部的刷新按钮 ---
        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(24, 0, 24, 16)
        
        self.refresh_btn = QPushButton("刷新统计与日志")
        self.refresh_btn.clicked.connect(self._start_refresh)   # 异步刷新
        bottom_layout.addWidget(self.refresh_btn)
        
        main_layout.addWidget(bottom_container)

        # 初次加载数据（异步）
        self._start_refresh()

    def _start_refresh(self):
        """启动后台刷新线程"""
        # 获取当前筛选的事件类型
        selected_display = self.event_type_combo.currentText()
        event_type_map = {
            "全部": None,
            "用户注册": "user.register",
            "用户登录": "user.login",
            "创建任务": "task.create",
            "任务开始分析": "task.processing",
            "任务完成": "task.completed",
            "任务失败": "task.failed",
            "提交反馈": "feedback.vote"
        }
        event_type = event_type_map.get(selected_display, None)

        # 禁用按钮，显示加载状态
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("加载中...")
        self.filter_btn.setEnabled(False)
        self.filter_btn.setText("加载中...")

        self.refresh_thread = RefreshStatsThread(self.api, event_type)
        self.refresh_thread.finished.connect(self._on_refresh_finished)
        self.refresh_thread.error.connect(self._on_refresh_error)
        self.refresh_thread.start()

    def _on_refresh_finished(self, stats, logs):
        """刷新成功回调"""
        # 更新统计卡片
        for key, label in self.stats_labels.items():
            val = stats.get(key, 0)
            label.setText(str(val))

        # 更新日志表格
        reverse_map = {
            "user.register": "用户注册",
            "user.login": "用户登录",
            "task.create": "创建任务",
            "task.processing": "任务开始分析",
            "task.completed": "任务完成",
            "task.failed": "任务失败",
            "feedback.vote": "提交反馈"
        }
        self.log_table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            self.log_table.setItem(row, 0, self._create_center_item(str(log["id"])))
            self.log_table.setItem(row, 1, self._create_center_item(str(log.get("user_id", ""))))
            raw_event = log.get("event_type", "")
            event_display = reverse_map.get(raw_event, raw_event)
            self.log_table.setItem(row, 2, self._create_center_item(event_display))
            self.log_table.setItem(row, 3, QTableWidgetItem(log.get("description", "")))
            self.log_table.setItem(row, 4, self._create_center_item(log.get("created_at", "")))

        # 恢复按钮
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("刷新统计与日志")
        self.filter_btn.setEnabled(True)
        self.filter_btn.setText("筛选")

    def _on_refresh_error(self, error_msg):
        """刷新失败回调"""
        QMessageBox.warning(self, "错误", f"刷新失败: {error_msg}")
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("刷新统计与日志")
        self.filter_btn.setEnabled(True)
        self.filter_btn.setText("筛选")

    def logout(self):
        self.api.logout()
        from ui.login_widget import LoginWidget
        self.login_window = LoginWidget()
        self.login_window.show()
        main_window = self.window()
        if main_window:
            main_window.close()