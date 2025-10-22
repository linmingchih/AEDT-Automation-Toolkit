import csv
import json
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)


class Table(QWidget):
    """Display the contents of the generated CCT CSV report."""

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self._current_project = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        source_group = QGroupBox("CCT Result")
        source_layout = QHBoxLayout(source_group)
        source_layout.addWidget(QLabel("CSV Path:"))
        self.csv_path_input = QLineEdit()
        self.csv_path_input.setReadOnly(True)
        source_layout.addWidget(self.csv_path_input)
        self.browse_button = QPushButton("Browse")
        source_layout.addWidget(self.browse_button)
        self.reload_button = QPushButton("Reload")
        source_layout.addWidget(self.reload_button)
        layout.addWidget(source_group)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.status_label = QLabel("No data loaded.")
        layout.addWidget(self.status_label)

    def bind_to_controller(self):
        self.reload_button.clicked.connect(self.reload)
        self.browse_button.clicked.connect(self.browse_csv)

    # ------------------------------------------------------------------ #
    # Interaction helpers
    # ------------------------------------------------------------------ #
    def browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CCT CSV file",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if path:
            self.load_csv(path)

    def reload(self):
        if self.csv_path_input.text() and os.path.exists(self.csv_path_input.text()):
            self.load_csv(self.csv_path_input.text())
        elif self._current_project:
            self.load_from_project(self._current_project)

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #
    def load_from_project(self, project_path):
        if not project_path or not os.path.exists(project_path):
            return

        try:
            with open(project_path, "r", encoding="utf-8") as handle:
                project_data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._log(f"Could not load project file: {exc}", "red")
            return

        self._current_project = project_path
        csv_path = project_data.get("cct_path")
        self.csv_path_input.setText(csv_path or "")
        if not csv_path:
            self._log("CCT CSV path not found in project file.", "orange")
            self._clear_table()
            return

        self.load_csv(csv_path)

    def load_csv(self, csv_path):
        csv_path = os.path.normpath(csv_path)
        self.csv_path_input.setText(csv_path)

        if not os.path.exists(csv_path):
            self._log(f"CCT CSV not found: {csv_path}", "red")
            self._clear_table()
            return

        try:
            with open(csv_path, "r", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                rows = list(reader)
        except OSError as exc:
            self._log(f"Could not read CCT CSV: {exc}", "red")
            self._clear_table()
            return

        if not rows:
            self._log("CCT CSV is empty.", "orange")
            self._clear_table()
            return

        headers = rows[0]
        data_rows = rows[1:]

        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for column in range(len(headers)):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)

        self.table.setRowCount(len(data_rows))
        for r_idx, row in enumerate(data_rows):
            for c_idx, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, c_idx, item)

        self.table.setSortingEnabled(True)
        self.status_label.setText(f"Loaded {len(data_rows)} rows from {os.path.basename(csv_path)}.")
        self._log(f"CCT results loaded from {csv_path}")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _clear_table(self):
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.status_label.setText("No data available.")

    def _log(self, message, color=None):
        if hasattr(self.controller, "log"):
            self.controller.log(message, color)
