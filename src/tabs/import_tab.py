from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
)
from PySide6.QtCore import Qt


class ImportTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        import_group = QGroupBox("Layout Import")
        import_group_layout = QGridLayout(import_group)

        # Row 1: Layout type selection
        self.brd_radio = QRadioButton(".brd")
        self.aedb_radio = QRadioButton(".aedb")
        self.brd_radio.setChecked(True)
        import_group_layout.addWidget(self.brd_radio, 0, 0)
        import_group_layout.addWidget(self.aedb_radio, 0, 1)

        # Row 2: Path selection
        self.open_layout_button = QPushButton("Open...")
        self.layout_path_label = QLabel("No design loaded")
        import_group_layout.addWidget(QLabel("Design:"), 1, 0)
        import_group_layout.addWidget(self.layout_path_label, 1, 1)
        import_group_layout.addWidget(self.open_layout_button, 1, 2)

        # Row 3: Stackup selection
        self.stackup_path_input = QLineEdit()
        self.browse_stackup_button = QPushButton("Browse...")
        import_group_layout.addWidget(QLabel("Stackup (.xml):"), 2, 0)
        import_group_layout.addWidget(self.stackup_path_input, 2, 1)
        import_group_layout.addWidget(self.browse_stackup_button, 2, 2)
        
        # EDB version input
        import_group_layout.addWidget(QLabel("EDB version:"), 3, 0)
        self.edb_version_input = QLineEdit()
        self.edb_version_input.setFixedWidth(60)
        import_group_layout.addWidget(self.edb_version_input, 3, 1)

        layout.addWidget(import_group)

        self.apply_import_button = QPushButton("Apply")
        primary_style = "background-color: #007bff; color: white; border: none;"
        self.apply_import_button.setStyleSheet(primary_style)
        self.apply_import_button_original_style = primary_style
        layout.addWidget(self.apply_import_button, alignment=Qt.AlignRight)

        layout.addStretch()
