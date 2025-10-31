import json
import os
import re
import sys

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QListWidget,
    QGroupBox,
    QListWidgetItem,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView

from .base import BaseTab


class NetListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.toggle_selected_items_check_state()
        else:
            super().keyPressEvent(event)

    def toggle_selected_items_check_state(self):
        selected_items = self.selectedItems()
        if not selected_items:
            return

        target_state = (
            Qt.Checked
            if selected_items[0].checkState() == Qt.Unchecked
            else Qt.Unchecked
        )

        for item in selected_items:
            item.setCheckState(target_state)
class PortSetupTab(BaseTab):
    def __init__(self, context):
        super().__init__(context)
        self.all_components = []
        self.setup_ui()

    def setup_ui(self):
        port_setup_layout = QVBoxLayout(self)
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Component filter (regex):"))
        self.component_filter_input = QLineEdit("^[UJ]")
        filter_layout.addWidget(self.component_filter_input)
        port_setup_layout.addLayout(filter_layout)

        components_layout = QHBoxLayout()
        self.controller_components_list = QListWidget()
        self.controller_components_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.dram_components_list = QListWidget()
        self.dram_components_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        controller_group = QGroupBox("Controller Components")
        controller_layout = QVBoxLayout(controller_group)
        controller_layout.addWidget(self.controller_components_list)
        dram_group = QGroupBox("DRAM Components")
        dram_layout = QVBoxLayout(dram_group)
        dram_layout.addWidget(self.dram_components_list)
        components_layout.addWidget(controller_group)
        components_layout.addWidget(dram_group)
        port_setup_layout.addLayout(components_layout)

        ref_net_layout = QHBoxLayout()
        ref_net_layout.addWidget(QLabel("Reference net:"))
        self.ref_net_combo = QComboBox()
        self.ref_net_combo.setMinimumWidth(150)
        self.ref_net_combo.addItems(["GND"])
        ref_net_layout.addWidget(self.ref_net_combo)
        ref_net_layout.addStretch()
        self.checked_nets_label = QLabel("Checked nets: 0 | Ports: 0")
        ref_net_layout.addWidget(self.checked_nets_label)
        port_setup_layout.addLayout(ref_net_layout)

        nets_layout = QHBoxLayout()
        single_ended_group = QGroupBox("Single-Ended Nets")
        self.single_ended_list = NetListWidget()
        single_ended_layout = QVBoxLayout(single_ended_group)
        single_ended_layout.addWidget(self.single_ended_list)
        differential_pairs_group = QGroupBox("Differential Pairs")
        self.differential_pairs_list = NetListWidget()
        differential_pairs_layout = QVBoxLayout(differential_pairs_group)
        differential_pairs_layout.addWidget(self.differential_pairs_list)
        nets_layout.addWidget(single_ended_group)
        nets_layout.addWidget(differential_pairs_group)
        port_setup_layout.addLayout(nets_layout)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setEnabled(False)
        primary_style = "background-color: #007bff; color: white; border: none;"
        self.apply_button.setStyleSheet(primary_style)
        self.apply_button_original_style = primary_style
        port_setup_layout.addWidget(self.apply_button, alignment=Qt.AlignRight)

    def bind_to_controller(self):
        self.component_filter_input.textChanged.connect(self.filter_components)
        self.controller_components_list.itemSelectionChanged.connect(self.update_nets)
        self.dram_components_list.itemSelectionChanged.connect(self.update_nets)
        self.single_ended_list.itemChanged.connect(self.update_checked_count)
        self.differential_pairs_list.itemChanged.connect(self.update_checked_count)
        self.apply_button.clicked.connect(self.apply_settings)

    def filter_components(self):
        pattern = self.component_filter_input.text()
        try:
            regex = re.compile(pattern)
        except re.error:
            return

        self.controller_components_list.clear()
        self.dram_components_list.clear()

        for comp_name, pin_count in self.all_components:
            if regex.search(comp_name):
                item_text = f"{comp_name} ({pin_count})"
                self.controller_components_list.addItem(item_text)
                self.dram_components_list.addItem(item_text)

    def update_checked_count(self):
        checked_single = sum(
            1
            for i in range(self.single_ended_list.count())
            if self.single_ended_list.item(i).checkState() == Qt.Checked
        )
        checked_diff = sum(
            1
            for i in range(self.differential_pairs_list.count())
            if self.differential_pairs_list.item(i).checkState() == Qt.Checked
        )
        checked_nets = checked_single + (checked_diff * 2)
        ports = (checked_single * 2) + (checked_diff * 4)
        self.checked_nets_label.setText(
            f"Checked nets: {checked_nets} | Ports: {ports}"
        )
        self.apply_button.setEnabled(checked_nets > 0)

    def load_pcb_data(self):
        controller = self.controller
        try:
            if not controller.project_file or not os.path.exists(
                controller.project_file
            ):
                controller.log("Project file not found.", "red")
                return

            with open(controller.project_file, "r") as handle:
                project_data = json.load(handle)

            controller.pcb_data = project_data.get("pcb_data")
            if not controller.pcb_data:
                controller.log("No pcb_data found in project file.", "orange")
                return

            self.controller_components_list.clear()
            self.dram_components_list.clear()
            if "component" in controller.pcb_data:
                self.all_components = [
                    (name, len(pins))
                    for name, pins in controller.pcb_data["component"].items()
                ]
                self.all_components.sort(key=lambda item: item[1], reverse=True)
                self.filter_components()
        except Exception as exc:
            controller.log(f"Error loading data: {exc}", "red")

    def update_nets(self):
        controller = self.controller
        pcb_data = controller.pcb_data
        if not pcb_data or "component" not in pcb_data:
            return

        selected_controllers = [
            item.text().split(" ")[0]
            for item in self.controller_components_list.selectedItems()
        ]
        selected_drams = [
            item.text().split(" ")[0]
            for item in self.dram_components_list.selectedItems()
        ]

        self.single_ended_list.blockSignals(True)
        self.differential_pairs_list.blockSignals(True)

        self.single_ended_list.clear()
        self.differential_pairs_list.clear()
        self.ref_net_combo.clear()

        try:
            if not selected_controllers or not selected_drams:
                self.ref_net_combo.addItem("GND")
                self.update_checked_count()
                return

            controller_nets = {
                pin[1]
                for comp in selected_controllers
                for pin in pcb_data["component"].get(comp, [])
            }
            dram_nets = {
                pin[1]
                for comp in selected_drams
                for pin in pcb_data["component"].get(comp, [])
            }
            common_nets = controller_nets.intersection(dram_nets)

            selected_components = selected_controllers + selected_drams
            net_pin_counts = {
                net: sum(
                    1
                    for comp_name in selected_components
                    for pin in pcb_data["component"].get(comp_name, [])
                    if pin[1] == net
                )
                for net in common_nets
            }
            sorted_nets = sorted(
                net_pin_counts.items(), key=lambda item: item[1], reverse=True
            )

            for net_name, _ in sorted_nets:
                self.ref_net_combo.addItem(net_name)
            if sorted_nets:
                self.ref_net_combo.setCurrentIndex(0)

            diff_pairs_info = pcb_data.get("diff", {})
            diff_pair_nets = {
                net for pos_net, neg_net in diff_pairs_info.values() for net in (pos_net, neg_net)
            }

            single_nets = sorted(
                [
                    net
                    for net in common_nets
                    if net not in diff_pair_nets and net.upper() != "GND"
                ]
            )
            for net in single_nets:
                item = QListWidgetItem(net)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.single_ended_list.addItem(item)

            for pair_name, (pos_net, neg_net) in sorted(diff_pairs_info.items()):
                if pos_net in common_nets and neg_net in common_nets:
                    item = QListWidgetItem(pair_name)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    self.differential_pairs_list.addItem(item)

            self.update_checked_count()
        finally:
            self.single_ended_list.blockSignals(False)
            self.differential_pairs_list.blockSignals(False)

    def apply_settings(self):
        controller = self.controller
        import_state = controller.get_tab_state("import_tab")

        if not controller.pcb_data:
            controller.log("No PCB data loaded.", "red")
            return

        project_data = {"app_name": controller.app_name}
        if controller.project_file and os.path.exists(controller.project_file):
            with open(controller.project_file, "r") as handle:
                project_data.update(json.load(handle))

        project_data.update(
            {
                "reference_net": self.ref_net_combo.currentText(),
                "controller_components": [
                    item.text().split(" ")[0]
                    for item in self.controller_components_list.selectedItems()
                ],
                "dram_components": [
                    item.text().split(" ")[0]
                    for item in self.dram_components_list.selectedItems()
                ],
                "ports": [],
            }
        )

        sequence = 1
        diff_pairs_info = controller.pcb_data.get("diff", {})

        signal_nets = []
        for idx in range(self.single_ended_list.count()):
            item = self.single_ended_list.item(idx)
            if item.checkState() == Qt.Checked:
                net_name = item.text()
                signal_nets.append(net_name)
                for comp in project_data["controller_components"]:
                    if any(
                        pin[1] == net_name
                        for pin in controller.pcb_data["component"].get(comp, [])
                    ):
                        project_data["ports"].append(
                            {
                                "sequence": sequence,
                                "name": f"{sequence}_{comp}_{net_name}",
                                "component": comp,
                                "component_role": "controller",
                                "net": net_name,
                                "net_type": "single",
                                "pair": None,
                                "polarity": None,
                                "reference_net": project_data["reference_net"],
                            }
                        )
                        sequence += 1
                for comp in project_data["dram_components"]:
                    if any(
                        pin[1] == net_name
                        for pin in controller.pcb_data["component"].get(comp, [])
                    ):
                        project_data["ports"].append(
                            {
                                "sequence": sequence,
                                "name": f"{sequence}_{comp}_{net_name}",
                                "component": comp,
                                "component_role": "dram",
                                "net": net_name,
                                "net_type": "single",
                                "pair": None,
                                "polarity": None,
                                "reference_net": project_data["reference_net"],
                            }
                        )
                        sequence += 1

        for idx in range(self.differential_pairs_list.count()):
            item = self.differential_pairs_list.item(idx)
            if item.checkState() == Qt.Checked:
                pair_name = item.text()
                p_net, n_net = diff_pairs_info[pair_name]
                signal_nets.extend([p_net, n_net])
                for comp in project_data["controller_components"]:
                    if any(
                        pin[1] == p_net
                        for pin in controller.pcb_data["component"].get(comp, [])
                    ):
                        project_data["ports"].append(
                            {
                                "sequence": sequence,
                                "name": f"{sequence}_{comp}_{p_net}",
                                "component": comp,
                                "component_role": "controller",
                                "net": p_net,
                                "net_type": "differential",
                                "pair": pair_name,
                                "polarity": "positive",
                                "reference_net": project_data["reference_net"],
                            }
                        )
                        sequence += 1
                for comp in project_data["dram_components"]:
                    if any(
                        pin[1] == p_net
                        for pin in controller.pcb_data["component"].get(comp, [])
                    ):
                        project_data["ports"].append(
                            {
                                "sequence": sequence,
                                "name": f"{sequence}_{comp}_{p_net}",
                                "component": comp,
                                "component_role": "dram",
                                "net": p_net,
                                "net_type": "differential",
                                "pair": pair_name,
                                "polarity": "positive",
                                "reference_net": project_data["reference_net"],
                            }
                        )
                        sequence += 1
                for comp in project_data["controller_components"]:
                    if any(
                        pin[1] == n_net
                        for pin in controller.pcb_data["component"].get(comp, [])
                    ):
                        project_data["ports"].append(
                            {
                                "sequence": sequence,
                                "name": f"{sequence}_{comp}_{n_net}",
                                "component": comp,
                                "component_role": "controller",
                                "net": n_net,
                                "net_type": "differential",
                                "pair": pair_name,
                                "polarity": "negative",
                                "reference_net": project_data["reference_net"],
                            }
                        )
                        sequence += 1
                for comp in project_data["dram_components"]:
                    if any(
                        pin[1] == n_net
                        for pin in controller.pcb_data["component"].get(comp, [])
                    ):
                        project_data["ports"].append(
                            {
                                "sequence": sequence,
                                "name": f"{sequence}_{comp}_{n_net}",
                                "component": comp,
                                "component_role": "dram",
                                "net": n_net,
                                "net_type": "differential",
                                "pair": pair_name,
                                "polarity": "negative",
                                "reference_net": project_data["reference_net"],
                            }
                        )
                        sequence += 1

        drams_with_ports = {
            port["component"]
            for port in project_data["ports"]
            if port["component_role"] == "dram"
        }
        project_data["dram_components"] = [
            comp for comp in project_data["dram_components"] if comp in drams_with_ports
        ]

        signal_nets_sorted = sorted(signal_nets)
        controller.publish_event(
            "ports.updated",
            {
                "signal_nets": signal_nets_sorted,
                "reference_net": project_data["reference_net"],
            },
        )
        controller.update_state(
            signal_nets=signal_nets_sorted,
            reference_net=project_data["reference_net"],
            ports_ready=bool(project_data["ports"]),
        )

        try:
            project_data["cct_ports_ready"] = bool(project_data["ports"])
            with open(controller.project_file, "w") as handle:
                json.dump(project_data, handle, indent=2)
            controller.log(
                f"Successfully saved to {controller.project_file}. Now applying to EDB..."
            )

            controller.set_button_running(self.apply_button)
            action_spec = controller.get_action_spec("set_edb", tab_name="port_setup_tab")
            script_path = action_spec["script"]
            python_executable = sys.executable
            edb_version = import_state.get("edb_version") or project_data.get(
                "edb_version", ""
            )

            command = [
                python_executable,
                script_path,
                controller.project_file,
                edb_version,
            ]
            if action_spec.get("args"):
                command.extend(action_spec["args"])

            metadata = {
                "type": "set_edb",
                "description": "Applying port definitions to EDB",
                "button": self.apply_button,
                "button_style": getattr(self, "apply_button_original_style", ""),
                "button_reset_text": "Apply",
            }

            controller.submit_task(
                command,
                metadata=metadata,
                input_path=controller.project_file,
                description=metadata["description"],
                working_dir=action_spec.get("working_dir"),
                env=action_spec.get("env"),
            )

        except Exception as exc:
            controller.log(f"Error during apply: {exc}", "red")
            controller.restore_button(
                self.apply_button,
                getattr(self, "apply_button_original_style", ""),
                "Apply",
            )
