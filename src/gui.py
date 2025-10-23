import os
import sys
import json
import importlib
from functools import partial
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QTabWidget,
    QTextEdit,
)
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl


class MainApplicationWindow(QMainWindow):
    BASE_TITLE = "AEDT Automation Toolkit"

    def __init__(self):
        super().__init__()
        self._update_window_title()
        self.setGeometry(100, 100, 1200, 800)

        self.current_controller = None
        self.apps = {}
        self.first_app_name = None

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Menu Bar ---
        menu_bar = self.menuBar()
        self.apps_menu = menu_bar.addMenu("Apps")
        self.tools_menu = menu_bar.addMenu("Tools")
        self.options_menu = menu_bar.addMenu("Options")

        self.stackup_editor_action = QAction("Stackup Editor", self)
        self.stackup_editor_action.triggered.connect(self.open_stackup_editor)
        self.tools_menu.addAction(self.stackup_editor_action)

        self.help_action = QAction("Help", self, checkable=True)
        self.help_action.toggled.connect(self.toggle_help_tab)
        self.options_menu.addAction(self.help_action)

        self.license_action = QAction("License", self, checkable=True)
        self.license_action.toggled.connect(self.toggle_license_tab)
        self.options_menu.addAction(self.license_action)

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

        # Load the first discovered app by default
        if self.first_app_name:
            self.switch_app(self.first_app_name)

    def open_stackup_editor(self):
        """
        Opens the stackup editor HTML file in the default web browser.
        """
        editor_path = os.path.join(os.path.dirname(__file__), "tools", "stackup_editor.html")
        if os.path.exists(editor_path):
            url = QUrl.fromLocalFile(os.path.abspath(editor_path))
            QDesktopServices.openUrl(url)
        else:
            self.log_window.append(f"Error: Could not find stackup editor at {editor_path}")

    def discover_apps(self):
        """
        Scans the 'apps' directory and populates the 'Apps' menu.
        """
        apps_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apps")
        if not os.path.isdir(apps_dir):
            return

        app_names = sorted(os.listdir(apps_dir))
        for app_name in app_names:
            app_path = os.path.join(apps_dir, app_name)
            config_path = os.path.join(app_path, "config.json")
            controller_path = os.path.join(app_path, "controller.py")

            if os.path.isdir(app_path) and os.path.exists(config_path) and os.path.exists(controller_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        display_name = config.get("display_name", app_name)
                        
                        if not self.first_app_name:
                            self.first_app_name = app_name

                        action = QAction(display_name, self)
                        action.triggered.connect(partial(self.switch_app, app_name))
                        self.apps_menu.addAction(action)
                        self.apps[app_name] = {
                            "display_name": display_name,
                            "config_path": config_path,
                        }

                except Exception as e:
                    print(f"Could not load app '{app_name}': {e}")

    def switch_app(self, app_name):
        """
        Loads the selected application's controller and tabs.
        """
        if not app_name:
            return

        # Clear existing tabs
        self.tabs.clear()
        self._update_window_title()

        # Dynamically import and instantiate the controller
        try:
            # Invalidate caches to ensure the latest controller is loaded
            importlib.invalidate_caches()
            controller_module_name = f"apps.{app_name}.controller"
            
            # If the module is already loaded, reload it
            if controller_module_name in sys.modules:
                controller_module = importlib.reload(sys.modules[controller_module_name])
            else:
                controller_module = importlib.import_module(controller_module_name)

            self.current_controller = controller_module.AppController(app_name)
            self.current_controller.log_window = self.log_window # Give controller access to the logger
        except Exception as e:
            self.log_window.setText(f"Error loading controller for '{app_name}': {e}")
            return

        # Load app config and create tabs
        app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apps", app_name)
        config_path = os.path.join(app_path, "config.json")
        app_meta = self.apps.get(app_name, {})

        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                display_name = config.get("display_name", app_meta.get("display_name", app_name))
                app_meta.update({
                    "display_name": display_name,
                    "config_path": config_path,
                })
                self.apps[app_name] = app_meta
                self._update_window_title(display_name)
                tabs_config = config.get("tabs", {})
                
                loaded_tabs = {}
                if isinstance(tabs_config, dict):
                    for tab_name, display_title in tabs_config.items():
                        tab_module_name = f"tabs.{tab_name}"
                        tab_module = importlib.import_module(tab_module_name)
                        
                        class_name = "".join(word.capitalize() for word in tab_name.split('_'))
                        tab_class = getattr(tab_module, class_name)
                        
                        tab_instance = tab_class(self.current_controller)
                        self.tabs.addTab(tab_instance, display_title)
                        loaded_tabs[tab_name] = tab_instance
                
                if hasattr(self.current_controller, "connect_signals"):
                    self.current_controller.connect_signals(loaded_tabs)
                
                if hasattr(self.current_controller, "load_config"):
                    self.current_controller.load_config()

                if self.help_action.isChecked():
                    self.toggle_help_tab(True)

                if self.license_action.isChecked():
                    self.toggle_license_tab(True)

        except Exception as e:
            self._update_window_title()
            self.log_window.setText(f"Error loading tabs for '{app_name}': {e}")
            return

    def toggle_help_tab(self, enabled):
        """Shows or hides the help tab for the current application."""
        HELP_TAB_NAME = "Help"
        # First, remove any existing help tab to ensure a clean state
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == HELP_TAB_NAME:
                self.tabs.removeTab(i)
                break

        if not enabled:
            return

        if not self.current_controller:
            return

        app_name = self.current_controller.app_name
        app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apps", app_name)
        help_file = os.path.join(app_path, "help.md")

        if not os.path.exists(help_file):
            return

        try:
            from tabs.help import HelpTab
            help_tab = HelpTab(self.current_controller)
            help_tab.load_help_content(help_file)
            self.tabs.addTab(help_tab, HELP_TAB_NAME)
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        except Exception as e:
            self.log_window.append(f"Could not load help tab: {e}")

    def toggle_license_tab(self, enabled):
        """Shows or hides the license tab."""
        LICENSE_TAB_NAME = "License"
        # First, remove any existing license tab to ensure a clean state
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == LICENSE_TAB_NAME:
                self.tabs.removeTab(i)
                break

        if not enabled:
            return

        try:
            from tabs.license_tab import LicenseTab
            license_tab = LicenseTab(self.current_controller)
            self.tabs.addTab(license_tab, LICENSE_TAB_NAME)
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        except Exception as e:
            self.log_window.append(f"Could not load license tab: {e}")

    def closeEvent(self, event):
        if self.current_controller and hasattr(self.current_controller, "save_config"):
            self.current_controller.save_config()
        super().closeEvent(event)

    def _update_window_title(self, app_display_name=None):
        if app_display_name:
            self.setWindowTitle(f"{self.BASE_TITLE} - {app_display_name}")
        else:
            self.setWindowTitle(self.BASE_TITLE)

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
