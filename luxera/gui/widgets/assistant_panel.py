from __future__ import annotations

from PySide6 import QtWidgets

from luxera.gui.widgets.copilot_panel import CopilotPanel


class AssistantPanel(CopilotPanel):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["Guide", "Autopilot", "Batch"])
        self.export_report = QtWidgets.QPushButton("Export report")
        self.export_audit_bundle = QtWidgets.QPushButton("Export audit bundle")
        self.activity_log = QtWidgets.QPlainTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setPlaceholderText("Tool and action log")
        self.design_options = QtWidgets.QComboBox()
        self.design_options.setPlaceholderText("No design options")
        self.design_iterate = QtWidgets.QPushButton("Iterate Solve")
        self.design_max_iters = QtWidgets.QSpinBox()
        self.design_max_iters.setRange(1, 20)
        self.design_max_iters.setValue(3)

        self.summary_cards = QtWidgets.QGroupBox("Output Summary")
        cards_layout = QtWidgets.QFormLayout(self.summary_cards)
        self.card_avg = QtWidgets.QLabel("-")
        self.card_u0 = QtWidgets.QLabel("-")
        self.card_status = QtWidgets.QLabel("-")
        cards_layout.addRow("Avg lux", self.card_avg)
        cards_layout.addRow("U0", self.card_u0)
        cards_layout.addRow("Status", self.card_status)

        self.tool_log_box = QtWidgets.QGroupBox("Tool Log")
        self.tool_log_box.setCheckable(True)
        self.tool_log_box.setChecked(False)
        tool_log_layout = QtWidgets.QVBoxLayout(self.tool_log_box)
        tool_log_layout.addWidget(self.activity_log)

        self.plan_group = QtWidgets.QGroupBox("Plan Checklist")
        plan_layout = QtWidgets.QVBoxLayout(self.plan_group)
        plan_layout.setContentsMargins(8, 8, 8, 8)
        plan_layout.addWidget(self.plan_view)

        self.diff_group = QtWidgets.QGroupBox("Diff Preview")
        diff_layout = QtWidgets.QVBoxLayout(self.diff_group)
        diff_layout.setContentsMargins(8, 8, 8, 8)
        diff_layout.addWidget(self.diff)
        diff_layout.addWidget(self.diff_details)
        toggles = QtWidgets.QHBoxLayout()
        toggles.addWidget(self.select_all)
        toggles.addWidget(self.select_none)
        toggles.addStretch(1)
        diff_layout.addLayout(toggles)

        self.apply_only.setText("Apply")
        self.apply_run.setText("Apply + Run")
        self.run_only.setText("Run")

        self.design_group = QtWidgets.QGroupBox("Design Solve")
        design_layout = QtWidgets.QFormLayout(self.design_group)
        design_layout.addRow("Option", self.design_options)
        design_layout.addRow("Max iters", self.design_max_iters)
        design_layout.addRow(self.design_iterate)

        layout = self.layout()
        if not isinstance(layout, QtWidgets.QVBoxLayout):
            return

        # Strip default order from base panel and rebuild task-panel layout.
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        layout.addWidget(self.mode)
        layout.addWidget(self.input)
        layout.addWidget(self.run)

        action_row = QtWidgets.QHBoxLayout()
        action_row.addWidget(self.apply_only)
        action_row.addWidget(self.run_only)
        action_row.addWidget(self.apply_run)
        layout.addLayout(action_row)

        history_row = QtWidgets.QHBoxLayout()
        history_row.addWidget(self.undo_assistant)
        history_row.addWidget(self.redo_assistant)
        layout.addLayout(history_row)

        layout.addWidget(self.plan_group)
        layout.addWidget(self.diff_group)
        layout.addWidget(self.summary_cards)
        layout.addWidget(self.design_group)
        layout.addWidget(self.output)
        layout.addWidget(self.audit)

        export_row = QtWidgets.QHBoxLayout()
        export_row.addWidget(self.export_report)
        export_row.addWidget(self.export_audit_bundle)
        layout.addLayout(export_row)

        layout.addWidget(self.tool_log_box)
        layout.addStretch(1)
