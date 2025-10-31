import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
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

from .base import BaseTab


class CctTab(BaseTab):
    DEFAULT_SETTINGS = {
        "tx_vhigh": 0.8,
        "tx_rise_time": 30.0,
        "unit_interval": 133.0,
        "tx_resistance": 40.0,
        "tx_capacitance": 1.0,
        "rx_resistance": 30.0,
        "rx_capacitance": 1.8,
        "transient_step": 100.0,
        "transient_stop": 3.0,
        "aedt_version": "2025.1",
        "sparam_threshold_db": -40.0,
    }

    FLOAT_FIELD_DECIMALS = {
        "tx_vhigh": 3,
        "tx_rise_time": 3,
        "unit_interval": 3,
        "tx_resistance": 3,
        "tx_capacitance": 3,
        "rx_resistance": 3,
        "rx_capacitance": 3,
        "transient_step": 3,
        "transient_stop": 3,
        "sparam_threshold_db": 1,
    }

    FIELD_LABELS = {
        "tx_vhigh": "TX Vhigh",
        "tx_rise_time": "TX Rise Time",
        "unit_interval": "Unit Interval",
        "tx_resistance": "TX Resistance",
        "tx_capacitance": "TX Capacitance",
        "rx_resistance": "RX Resistance",
        "rx_capacitance": "RX Capacitance",
        "transient_step": "Transient Step",
        "transient_stop": "Transient Stop",
        "aedt_version": "AEDT Version",
        "sparam_threshold_db": "Threshold (dB)",
    }

    def __init__(self, context):
        super().__init__(context)
        self._field_widgets = {}
        self.setup_ui()
        self._apply_settings_to_inputs({})
        self._clear_port_table()

    # ------------------------------------------------------------------ #
    # UI setup
    # ------------------------------------------------------------------ #
    def setup_ui(self):
        layout = QVBoxLayout(self)

        data_group = QGroupBox("Data Sources")
        data_layout = QGridLayout(data_group)
        data_layout.addWidget(QLabel("Touchstone (.sNp):"), 0, 0)
        self.touchstone_path_input = QLineEdit()
        data_layout.addWidget(self.touchstone_path_input, 0, 1)
        self.touchstone_browse_button = QPushButton("Browse")
        data_layout.addWidget(self.touchstone_browse_button, 0, 2)

        data_layout.addWidget(QLabel("Port metadata (.json):"), 1, 0)
        self.project_path_input = QLineEdit()
        data_layout.addWidget(self.project_path_input, 1, 1)
        self.project_browse_button = QPushButton("Browse")
        data_layout.addWidget(self.project_browse_button, 1, 2)
        layout.addWidget(data_group)

        settings_row = QHBoxLayout()
        settings_row.addWidget(self._build_tx_group())
        settings_row.addWidget(self._build_rx_group())
        settings_row.addWidget(self._build_transient_group())
        settings_row.addWidget(self._build_options_group())
        layout.addLayout(settings_row)

        port_group = QGroupBox("Port Information")
        port_layout = QVBoxLayout(port_group)
        self.port_table = QTableWidget(0, 5)
        self.port_table.setHorizontalHeaderLabels(["#", "TX Port", "RX Port", "Type", "Pair"])
        header = self.port_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        self.port_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.port_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.port_table.setAlternatingRowColors(True)
        port_layout.addWidget(self.port_table)
        self.port_status_label = QLabel("Port setup not yet applied.")
        self.port_status_label.setAlignment(Qt.AlignLeft)
        self.port_status_label.setWordWrap(True)
        port_layout.addWidget(self.port_status_label)
        layout.addWidget(port_group)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        self.apply_button = QPushButton("Apply")
        primary_style = "background-color: #007bff; color: white; border: none;"
        self.apply_button.setStyleSheet(primary_style)
        self.apply_button_original_style = primary_style
        buttons_layout.addWidget(self.apply_button)
        layout.addLayout(buttons_layout)

    def _build_tx_group(self):
        group = QGroupBox("TX Settings")
        grid = QGridLayout(group)

        self.tx_vhigh_input = QLineEdit()
        self._add_labeled_field(grid, "TX Vhigh", self.tx_vhigh_input, "V", row=0)
        self.tx_rise_time_input = QLineEdit()
        self._add_labeled_field(grid, "TX Rise Time", self.tx_rise_time_input, "ps", row=1)
        self.unit_interval_input = QLineEdit()
        self._add_labeled_field(grid, "Unit Interval", self.unit_interval_input, "ps", row=2)
        self.tx_resistance_input = QLineEdit()
        self._add_labeled_field(grid, "TX Resistance", self.tx_resistance_input, "ohm", row=3)
        self.tx_capacitance_input = QLineEdit()
        self._add_labeled_field(grid, "TX Capacitance", self.tx_capacitance_input, "pF", row=4)

        self._field_widgets.update(
            {
                "tx_vhigh": self.tx_vhigh_input,
                "tx_rise_time": self.tx_rise_time_input,
                "unit_interval": self.unit_interval_input,
                "tx_resistance": self.tx_resistance_input,
                "tx_capacitance": self.tx_capacitance_input,
            }
        )
        return group

    def _build_rx_group(self):
        group = QGroupBox("RX Settings")
        grid = QGridLayout(group)

        self.rx_resistance_input = QLineEdit()
        self._add_labeled_field(grid, "RX Resistance", self.rx_resistance_input, "ohm", row=0)
        self.rx_capacitance_input = QLineEdit()
        self._add_labeled_field(grid, "RX Capacitance", self.rx_capacitance_input, "pF", row=1)

        self._field_widgets.update(
            {
                "rx_resistance": self.rx_resistance_input,
                "rx_capacitance": self.rx_capacitance_input,
            }
        )
        return group

    def _build_transient_group(self):
        group = QGroupBox("Transient Settings")
        grid = QGridLayout(group)

        self.transient_step_input = QLineEdit()
        self._add_labeled_field(grid, "Transient Step", self.transient_step_input, "ps", row=0)
        self.transient_stop_input = QLineEdit()
        self._add_labeled_field(grid, "Transient Stop", self.transient_stop_input, "ns", row=1)

        self._field_widgets.update(
            {
                "transient_step": self.transient_step_input,
                "transient_stop": self.transient_stop_input,
            }
        )
        return group

    def _build_options_group(self):
        group = QGroupBox("Options")
        grid = QGridLayout(group)

        self.aedt_version_input = QLineEdit()
        self._add_labeled_field(grid, "AEDT Version", self.aedt_version_input, "", row=0)
        self.threshold_input = QLineEdit()
        self._add_labeled_field(grid, "Threshold", self.threshold_input, "dB", row=1)

        self._field_widgets.update(
            {
                "aedt_version": self.aedt_version_input,
                "sparam_threshold_db": self.threshold_input,
            }
        )
        return group

    def _add_labeled_field(self, layout, label, widget, unit, row):
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(widget, row, 1)
        if unit:
            layout.addWidget(QLabel(unit), row, 2)
        else:
            layout.addWidget(QLabel(""), row, 2)

    # ------------------------------------------------------------------ #
    # Controller bindings
    # ------------------------------------------------------------------ #
    def bind_to_controller(self):
        self.touchstone_browse_button.clicked.connect(self.browse_touchstone)
        self.project_browse_button.clicked.connect(self.browse_project)
        self.apply_button.clicked.connect(self.apply_cct)

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #
    def browse_touchstone(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Touchstone File",
            "",
            "Touchstone files (*.sNp *.s1p *.s2p *.s3p *.s4p *.s5p *.s6p *.s7p *.s8p *.s9p *.s10p);;All files (*)",
        )
        if path:
            self.touchstone_path_input.setText(path)

    def browse_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Port Metadata (project.json)",
            "",
            "JSON files (*.json)",
        )
        if path:
            self.load_from_project(path)

    def apply_cct(self):
        controller = self.controller
        project_path = self.project_path_input.text().strip() or controller.project_file
        if not project_path:
            controller.log("Please select a project.json file before running the CCT calculation.", "red")
            return
        if not os.path.exists(project_path):
            controller.log(f"Project file not found: {project_path}", "red")
            return

        try:
            with open(project_path, "r", encoding="utf-8") as handle:
                project_data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            controller.log(f"Could not read project file: {exc}", "red")
            return

        ports = project_data.get("ports") or []
        ports_ready = bool(project_data.get("cct_ports_ready"))
        if not ports_ready:
            controller.log("Port setup has not been applied yet. Complete the Port Setup tab before running CCT.", "red")
            return
        if not ports:
            controller.log("No port definitions found in project.json. Complete the Port Setup tab before running CCT.", "red")
            return

        try:
            settings = self._collect_settings()
        except ValueError as exc:
            controller.log(str(exc), "red")
            return

        touchstone_path = self.touchstone_path_input.text().strip()
        if not touchstone_path:
            controller.log("Please specify the Touchstone (.sNp) file path.", "red")
            return
        if not os.path.exists(touchstone_path):
            controller.log(f"Touchstone file not found: {touchstone_path}", "red")
            return

        project_data["touchstone_path"] = os.path.normpath(touchstone_path)
        project_data["cct_settings"] = settings

        try:
            with open(project_path, "w", encoding="utf-8") as handle:
                json.dump(project_data, handle, indent=2)
        except OSError as exc:
            controller.log(f"Could not write project file: {exc}", "red")
            return

        controller.project_file = project_path
        self._update_port_information(True, ports)
        controller.log(f"CCT settings saved to {project_path}")

        self._start_cct_process(project_path)

    def _start_cct_process(self, project_path):
        controller = self.controller
        action_spec = controller.get_action_spec("run_cct", tab_name="cct_tab")
        script_path = action_spec["script"]
        command = [sys.executable, script_path, project_path]
        if action_spec.get("args"):
            command.extend(action_spec["args"])

        metadata = {
            "type": "run_cct",
            "description": "Running CCT calculation",
            "button": self.apply_button,
            "button_style": getattr(self, "apply_button_original_style", ""),
            "button_reset_text": "Apply",
        }

        controller.set_button_running(self.apply_button)
        task_id = controller.submit_task(
            command,
            metadata=metadata,
            input_path=project_path,
            description=metadata["description"],
            working_dir=action_spec.get("working_dir"),
            env=action_spec.get("env"),
        )

        if task_id is None:
            controller.restore_button(
                self.apply_button,
                getattr(self, "apply_button_original_style", ""),
                "Apply",
            )

    # ------------------------------------------------------------------ #
    # Data loading helpers
    # ------------------------------------------------------------------ #
    def load_from_project(self, project_path):
        if not project_path or not os.path.exists(project_path):
            return

        try:
            with open(project_path, "r", encoding="utf-8") as handle:
                project_data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self.controller.log(f"Could not load project data: {exc}", "red")
            return

        self.project_path_input.setText(project_path)
        self.controller.project_file = project_path

        touchstone_path = project_data.get("touchstone_path") or ""
        self.touchstone_path_input.setText(touchstone_path)

        self._apply_settings_to_inputs(project_data.get("cct_settings") or {})
        ports = project_data.get("ports") or []
        ports_ready = bool(project_data.get("cct_ports_ready"))
        self._update_port_information(ports_ready, ports)

    def populate_port_table(self, ports):
        rows = self._build_port_rows(ports or [])
        self.port_table.setSortingEnabled(False)
        self.port_table.setColumnCount(5)
        self.port_table.setHorizontalHeaderLabels(["#", "TX Port", "RX Port", "Type", "Pair"])
        self.port_table.setRowCount(len(rows))

        columns = ["index", "tx", "rx", "type", "pair"]
        for row_index, row in enumerate(rows):
            for col_index, key in enumerate(columns):
                item = QTableWidgetItem(str(row.get(key, "")))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.port_table.setItem(row_index, col_index, item)

        self.port_table.setSortingEnabled(True)
        self.port_status_label.setText(f"Loaded {len(rows)} port entries.")

    def _clear_port_table(self):
        self.port_table.setSortingEnabled(False)
        self.port_table.clearContents()
        self.port_table.setRowCount(0)
        self.port_table.setSortingEnabled(True)
        self.port_status_label.setText("Port setup not yet applied.")

    def _update_port_information(self, ports_ready, ports):
        if not ports_ready:
            self._clear_port_table()
            return
        self.populate_port_table(ports)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _apply_settings_to_inputs(self, settings):
        for key, decimals in self.FLOAT_FIELD_DECIMALS.items():
            widget = self._field_widgets.get(key)
            if not widget:
                continue
            value = settings.get(key, self.DEFAULT_SETTINGS.get(key))
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = float(self.DEFAULT_SETTINGS.get(key, 0.0))
            widget.setText(f"{value:.{decimals}f}")

        aedt_version = settings.get("aedt_version", self.DEFAULT_SETTINGS["aedt_version"])
        aedt_widget = self._field_widgets.get("aedt_version")
        if aedt_widget:
            aedt_widget.setText(str(aedt_version))

    def _collect_settings(self):
        settings = {}
        for key, decimals in self.FLOAT_FIELD_DECIMALS.items():
            widget = self._field_widgets.get(key)
            value = self._parse_float(widget, key)
            settings[key] = round(value, decimals)

        aedt_widget = self._field_widgets.get("aedt_version")
        aedt_version = aedt_widget.text().strip() if aedt_widget else ""
        settings["aedt_version"] = aedt_version or self.DEFAULT_SETTINGS["aedt_version"]
        return settings

    def _parse_float(self, widget, key):
        if widget is None:
            raise ValueError(f"Missing widget for {key}")

        text = widget.text().strip()
        if not text:
            return float(self.DEFAULT_SETTINGS.get(key, 0.0))

        try:
            return float(text)
        except ValueError as exc:
            label = self.FIELD_LABELS.get(key, key)
            raise ValueError(f"Invalid numeric value for {label}: '{text}'") from exc

    def _build_port_rows(self, ports):
        singles = {}
        differentials = {}

        for port in ports:
            net_type = str(port.get("net_type") or "").lower()
            role = str(port.get("component_role") or "").lower()
            sequence = port.get("sequence")
            name = port.get("name") or ""

            if net_type == "single":
                record = singles.setdefault(
                    port.get("net"),
                    {"tx": None, "rx": None, "tx_seq": None, "rx_seq": None},
                )
                if role == "controller":
                    record["tx"] = name
                    record["tx_seq"] = sequence
                elif role == "dram":
                    record["rx"] = name
                    record["rx_seq"] = sequence

            elif net_type == "differential":
                pair_name = port.get("pair") or port.get("net")
                record = differentials.setdefault(
                    pair_name,
                    {
                        "tx_pos": None,
                        "tx_neg": None,
                        "rx_pos": None,
                        "rx_neg": None,
                        "tx_pos_seq": None,
                        "tx_neg_seq": None,
                        "rx_pos_seq": None,
                        "rx_neg_seq": None,
                    },
                )
                polarity = str(port.get("polarity") or "").lower()
                if role not in {"controller", "dram"} or polarity not in {"positive", "negative"}:
                    continue

                prefix = "tx" if role == "controller" else "rx"
                suffix = "pos" if polarity == "positive" else "neg"
                record[f"{prefix}_{suffix}"] = name
                record[f"{prefix}_{suffix}_seq"] = sequence

        def order_key(*values):
            numeric = [v for v in values if isinstance(v, (int, float))]
            return min(numeric) if numeric else float("inf")

        rows = []
        ordered = []
        for net, record in singles.items():
            ordered.append(
                (
                    order_key(record.get("tx_seq"), record.get("rx_seq")),
                    {
                        "tx": record.get("tx") or "",
                        "rx": record.get("rx") or "",
                        "type": "Single",
                        "pair": net or "",
                    },
                )
            )

        for pair, record in differentials.items():
            tx_ports = " / ".join(filter(None, [record.get("tx_pos"), record.get("tx_neg")]))
            rx_ports = " / ".join(filter(None, [record.get("rx_pos"), record.get("rx_neg")]))
            ordered.append(
                (
                    order_key(
                        record.get("tx_pos_seq"),
                        record.get("tx_neg_seq"),
                        record.get("rx_pos_seq"),
                        record.get("rx_neg_seq"),
                    ),
                    {
                        "tx": tx_ports,
                        "rx": rx_ports,
                        "type": "Differential",
                        "pair": pair or "",
                    },
                )
            )

        ordered.sort(key=lambda item: (item[0], item[1]["pair"]))
        for index, (_, row) in enumerate(ordered, 1):
            row["index"] = index
            rows.append(row)

        return rows
