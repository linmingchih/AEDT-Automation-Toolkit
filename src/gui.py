import os
import sys
import json
import importlib
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QTabWidget,
    QTextEdit,
    QComboBox,
    QLabel,
)

class MainApplicationWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SI Simulation Toolkit")
        self.setGeometry(100, 100, 1200, 800)

        self.current_controller = None
        self.apps = {}

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # App Selector
        app_selector_layout = QHBoxLayout()
        app_selector_layout.addWidget(QLabel("Select App:"))
        self.app_combo = QComboBox()
        self.app_combo.currentIndexChanged.connect(self.switch_app)
        app_selector_layout.addWidget(self.app_combo)
        app_selector_layout.addStretch(1)
        main_layout.addLayout(app_selector_layout)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Log Window
        log_group = QGroupBox("Information")
        log_group.setObjectName("logGroup")
        log_layout = QVBoxLayout(log_group)
        self.log_window = QTextEdit()
        self.log_window.setReadOnly(True)
        self.log_window.setObjectName("logWindow")
        log_layout.addWidget(self.log_window)
        main_layout.addWidget(log_group)

        self.apply_styles()
        self.discover_apps()

        if self.apps:
            self.app_combo.setCurrentIndex(0)
            self.switch_app(0)

    def discover_apps(self):
        """
        Scans the 'apps' directory to find available applications.
        """
        apps_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apps")
        if not os.path.isdir(apps_dir):
            return

        for app_name in os.listdir(apps_dir):
            app_path = os.path.join(apps_dir, app_name)
            config_path = os.path.join(app_path, "config.json")
            controller_path = os.path.join(app_path, "controller.py")

            if os.path.isdir(app_path) and os.path.exists(config_path) and os.path.exists(controller_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        display_name = config.get("display_name", app_name)
                        self.apps[display_name] = app_name
                        self.app_combo.addItem(display_name)
                except Exception as e:
                    print(f"Could not load app '{app_name}': {e}")

    def switch_app(self, index):
        """
        Loads the selected application's controller and tabs.
        """
        display_name = self.app_combo.itemText(index)
        app_name = self.apps.get(display_name)
        if not app_name:
            return

        # Clear existing tabs
        self.tabs.clear()

        # Dynamically import and instantiate the controller
        try:
            controller_module_name = f"apps.{app_name}.controller"
            controller_module = importlib.import_module(controller_module_name)
            self.current_controller = controller_module.AppController(app_name)
            self.current_controller.log_window = self.log_window # Give controller access to the logger
        except Exception as e:
            self.log_window.setText(f"Error loading controller for '{app_name}': {e}")
            return

        # Load app config and create tabs
        app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apps", app_name)
        config_path = os.path.join(app_path, "config.json")
        
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                tab_names = config.get("tabs", [])
                
                loaded_tabs = {}
                for tab_name in tab_names:
                    tab_module_name = f"tabs.{tab_name}"
                    tab_module = importlib.import_module(tab_module_name)
                    
                    # Assuming the class name is CamelCase version of the file name
                    # e.g., import_tab.py -> ImportTab
                    class_name = "".join(word.capitalize() for word in tab_name.split('_'))
                    tab_class = getattr(tab_module, class_name)
                    
                    # Pass the controller to the tab instance
                    tab_instance = tab_class(self.current_controller)
                    self.tabs.addTab(tab_instance, " ".join(word.capitalize() for word in tab_name.split('_')))
                    loaded_tabs[tab_name] = tab_instance
                
                # Pass tab instances to controller for signal connection
                if hasattr(self.current_controller, "connect_signals"):
                    self.current_controller.connect_signals(loaded_tabs)
                
                # Load app-specific data
                if hasattr(self.current_controller, "load_config"):
                    self.current_controller.load_config()

        except Exception as e:
            self.log_window.setText(f"Error loading tabs for '{app_name}': {e}")

    def closeEvent(self, event):
        if self.current_controller and hasattr(self.current_controller, "save_config"):
            self.current_controller.save_config()
        super().closeEvent(event)

    def apply_styles(self):
        self.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
            QGroupBox#logGroup {
                padding: 12px 2px 2px 2px;
                margin: 10px 0 0 0;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QGroupBox#logGroup::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 4px;
            }
            QTextEdit#logWindow {
                border: none;
                padding: 0;
                margin: 0;
            }
        """)
