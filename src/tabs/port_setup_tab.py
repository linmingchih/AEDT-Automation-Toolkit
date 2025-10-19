from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QListWidget,
    QGroupBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView

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


class PortSetupTab(QWidget):
    def __init__(self):
        super().__init__()
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
