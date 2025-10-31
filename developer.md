# 開發者指南（傳統中文）

> 本文件面向希望擴充 AEDT Automation Toolkit 的開發者，內容涵蓋專案結構、運作原理、常用工具與擴充流程。建議在開始開發前完整閱讀，以便快速理解系統運作方式。

## 目錄
1. [快速開始與環境設定](#快速開始與環境設定)
2. [專案結構總覽](#專案結構總覽)
3. [執行流程與資料流](#執行流程與資料流)
4. [核心架構詳細說明](#核心架構詳細說明)
    1. [GUI 主程式 (`src/gui.py`)](#gui-主程式-srcguipy)
    2. [Tab 與 UI 元件 (`src/tabs/`)](#tab-與-ui-元件-srctabs)
    3. [控制器 (`apps/<app>/controller.py`)](#控制器-appsappcontrollerpy)
    4. [服務層 (`src/services/`)](#服務層-srcservices)
    5. [自動化腳本 (`src/scripts/`)](#自動化腳本-srcscripts)
5. [`project.json` 契約與資料欄位](#projectjson-契約與資料欄位)
6. [新增 App 的完整範例流程](#新增-app-的完整範例流程)
7. [UI 與事件溝通守則](#ui-與事件溝通守則)
8. [編寫外部腳本的最佳實務](#編寫外部腳本的最佳實務)
9. [偵錯、記錄與常用工具](#偵錯記錄與常用工具)
10. [進一步閱讀與參考資源](#進一步閱讀與參考資源)

---

## 快速開始與環境設定

1. **Python 版本**：建議使用 Python 3.10 以上版本，以確保與 PySide6、PyAEDT 相容。
2. **建立虛擬環境**：
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows 上可改用 .venv\Scripts\activate
   pip install -U pip
   pip install -r requirements.txt
   ```
   主要依賴包括 PySide6（GUI）、PyAEDT / pyEDB（與 AEDT 溝通）等。
3. **啟動介面**：
   ```bash
   python src/main.py
   ```
   Windows 使用者亦可執行 `main.bat`。當 GUI 啟動後，左上角「Apps」選單會列出所有可用的流程。
4. **開發環境提示**：
   * 建議在具備 AEDT 的工作站或連線到 AEDT 的遠端環境中測試腳本。
   * `install.ps1` 提供 Windows 使用者的快速依賴安裝腳本，可視需求調整。

---

## 專案結構總覽

專案採模組化設計，以便快速擴充。下表列出重要目錄：

| 路徑 | 說明 |
| --- | --- |
| `apps/` | 每個 App 的設定與控制器，例如 `si_app`、`cct`。內含 `config.json`（描述 UI tab 列表）與 `controller.py`（流程邏輯）。 |
| `src/gui.py` | GUI 進入點，負責掃描 `apps/`、載入控制器與 UI Tabs。 |
| `src/main.py` | 應用程式主入口，建立 `QApplication` 並顯示主視窗。 |
| `src/tabs/` | 可重複使用的 UI 元件（各 Tab）。例如 `import_tab.py`、`simulation_tab.py`、`result_tab.py` 等。 |
| `src/controllers/` | 控制器共用邏輯，包括 `base_controller.py` 與 `tab_context.py`。 |
| `src/services/` | 輔助服務：`AppStateStore`（偏好設定儲存）、`ExternalScriptRunner`（外部腳本佇列與監控）。 |
| `src/scripts/` | 執行實際自動化任務的腳本，例如 `get_edb.py`、`set_sim.py`、`run_sim.py`、`generate_report.py`。 |
| `src/tools/stackup_editor.html` | 內建 Stackup 編輯器的靜態頁面，可從 GUI 的 Tools > Stackup Editor 開啟。 |
| `architecture.md` | 另一份概念性架構圖解，可與本文件交叉參考。 |
| `images/` | 文件或 GUI 使用的圖片資源。 |
| `temp/` | 執行期間產生的臨時專案資料夾，內含 `project.json`、堆疊 XML、模擬結果等。 |

---

## 執行流程與資料流

系統核心理念是「**三層分離**」與「**以 `project.json` 串聯整個流程**」：

1. **建立工作目錄**：`ImportTab` 會將使用者選擇的 `.brd` 或 `.aedb` 檔案複製到 `temp/<app>_<timestamp>/` 下，同時建立初始的 `project.json`。
2. **腳本串聯**：每個控制器會依序提交外部腳本（透過 `ExternalScriptRunner`）。腳本接收 `project.json` 路徑，讀取所需參數並更新結果。
3. **UI 回饋**：腳本完成後，控制器根據回傳的資料更新各 Tab（例如導入 PCB 資訊、更新堆疊、載入 Touchstone 檔、顯示報表）。

此流程讓 UI、流程控制與實際計算完全解耦，新增 App 時無須修改核心 GUI。

---

## 核心架構詳細說明

### GUI 主程式 (`src/gui.py`)
* 啟動時自動掃描 `apps/` 目錄，依 `config.json` 建立選單項目並保存 `display_name`、`description`。
* 切換 App 時：
  1. 動態載入 `apps.<app>.controller.AppController`。
  2. 讀取 `config.json` 的 `tabs` 配置，對應到 `src/tabs/<tab_name>.py` 的類別（以底線分詞 + 每字首字母大寫轉為類別名，例如 `import_tab` -> `ImportTab`）。
  3. 為每個 Tab 建立 `TabContext`，並注入控制器提供的 API。
  4. 透過控制器的 `connect_signals()`，讓 Tab 有機會註冊事件、設定 UI 回呼。
* 內建「Help」與「License」兩種可選擇顯示的附加頁籤，對應 `apps/<app>/help.md` 與 `tabs/license_tab.py`。
* 底部的訊息視窗 (`QTextEdit`) 會顯示控制器與腳本傳來的日誌。

### Tab 與 UI 元件 (`src/tabs`)
* 所有 Tab 類別皆繼承 `BaseTab`，其建構子會收到 `TabContext`。`BaseTab` 仍保留 `self.controller` 別名以相容既有程式碼。
* `TabContext` 封裝了常用操作：
  - `log()`：寫入 GUI 與專案 log。
  - `publish_event()` / `subscribe()`：在 Tab 之間傳遞事件。
  - `update_state()` / `get_state()` / `get_tab_state()`：儲存與讀取 Tab 層級狀態。
  - `submit_task()`：排程外部腳本執行，會回傳 task id。
  - `request_project_update()`：向控制器回報 `project.json` 相關的狀態更新。
* 現有 Tabs 可作為設計參考：
  - `import_tab.py`：負責建立 `project.json`、導入堆疊與呼叫 `get_edb.py`/`modify_xml.py`。
  - `port_setup_tab.py`：提供埠設定表格，並透過事件 `"ports.updated"` 將資料發佈給控制器。
  - `simulation_tab.py`：設定模擬參數（切除範圍、頻率掃描、版本）。
  - `result_tab.py`：載入 Touchstone、觸發報表產生 (`generate_report.py`)。
  - `cct_tab.py` / `table.py`：顯示 CCT 結果與表格資訊。

### 控制器 (`apps/<app>/controller.py`)
* 所有控制器繼承 `BaseAppController`：
  - 管理 `project_file`、`current_layout_path`、`report_path` 等流程狀態。
  - 透過 `register_task_handlers()` 註冊腳本完成/失敗的 callback。
  - `configure_tab_events()` 回傳允許每個 Tab 發佈的事件集合，可避免未授權的跨 Tab 溝通。
  - 提供 `get_action_spec()` 解析 `config.json` 中自訂的腳本參數（含 `script`、`args`、`working_dir`、`env`）。
  - `save_config()` / `load_config()` 預設使用 `AppStateStore` 儲存使用者偏好（例如上次的 EDB 版本、頻率掃描設定）。
* 參考 `apps/si_app/controller.py` 可了解完整流程：
  1. `get_edb` 導入佈線、生成堆疊 XML、讀取 PCB 資訊。
  2. `set_edb` 建立埠與參考端口。
  3. `set_sim` 設定切除與求解器參數，再自動排程 `run_sim`。
  4. `run_cct`、`get_loss`、`generate_report` 則提供進階分析與報表。
* 控制器負責將 `ExternalScriptRunner` 送出的日誌寫入 GUI，並在腳本完成後更新 Tab 狀態，例如重新載入結果頁籤、顯示報表路徑等。

### 服務層 (`src/services`)
* `AppStateStore`：
  - 依平台選擇適當的使用者資料夾（Windows `AppData/Roaming`、macOS `Library/Application Support`、Linux `~/.config`）。
  - 以 `{base_dir}/{app_name}/state.json` 儲存資料，可儲存 GUI 設定（如頻率掃描表格內容）。
* `ExternalScriptRunner`：
  - 以佇列管理外部命令 (`QProcess`)，確保 GUI 不被阻塞。
  - 透過 `run_task()` 接受指令、工作目錄、環境變數、重試次數等設定。
  - 發出 `started`、`finished`、`error`、`log_message` 訊號，由控制器接收並更新 UI。
  - 支援阻塞式執行（`blocking=True`）以及任務取消 (`cancel_task`)。

### 自動化腳本 (`src/scripts`)
* 每個腳本皆為獨立的 Python 檔案，僅以 `project.json` 交換資料。
* 現成腳本示例：
  - `get_edb.py`：導入設計、抓取元件/差分對資訊、輸出堆疊 XML。
  - `set_edb.py`：根據 `controller_components`、`ports` 建立埠與參考端口。
  - `set_sim.py`：配置切除範圍與求解器掃描（支援 SIwave、HFSS）。
  - `run_sim.py`：透過 PyAEDT 觸發 3D Layout 模擬並匯出 Touchstone。
  - `run_cct.py` / `get_loss.py`：執行進階分析，將結果寫回 `project.json`。
  - `generate_report.py`：根據結果生成 HTML 報表，GUI 會自動開啟。
* 編寫腳本時務必遵循「讀 `project.json` → 執行任務 → 寫回 `project.json`」的原則，避免保留任何全域狀態。

---

## `project.json` 契約與資料欄位

`project.json` 是所有腳本與 UI 溝通的唯一資料來源。以下列出常見欄位（實際欄位可依需求擴充，但請在文件或 PR 中註明）：

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `aedb_path` | `str` | 佈線檔案或導入後的 `.aedb` 路徑。`get_edb.py` 會在讀取 `.brd` 後轉換為 `.aedb`。 |
| `edb_version` | `str` | 指定 pyEDB / AEDT 版本。由 `ImportTab` 及 `set_sim.py` 使用。 |
| `stackup_path` | `str` | 使用者提供的新堆疊 XML 路徑。 |
| `xml_path` | `str` | `get_edb.py` 匯出的堆疊 XML。
| `pcb_data` | `dict` | `get_edb.py` 擷取的 PCB 資訊，包括 `component` 與 `diff`。 |
| `ports` | `list` | 由 `port_setup_tab.py` 生成的埠設定，`set_edb.py` 與模擬腳本會使用。 |
| `controller_components` / `dram_components` | `list` | 參考埠設定所需的元件清單。 |
| `reference_net` | `str` | 埠的參考網路。 |
| `cutout` | `dict` | 切除設定（是否啟用、信號/參考網路、擴張距離）。由 `set_sim.py` 讀取。 |
| `frequency_sweeps` | `list` | 頻率掃描設定（`[type, start, stop, step]`）。 |
| `solver` / `solver_version` | `str` | 指定使用的求解器與版本。 |
| `touchstone_path` | `str` | `run_sim.py` 生成的 Touchstone 檔案路徑。 |
| `result` | `dict` | `get_loss.py` 等腳本寫入的分析結果，供報表或後續工具使用。 |
| `report_path` | `str` | `generate_report.py` 生成的 HTML 報表位置。 |
| `cct_ports_ready` | `bool` | CCT 相關腳本是否已準備完成。 |

### 生命週期
1. **建立**：`ImportTab` 建立含 `aedb_path`、`edb_version` 等基本欄位的檔案。
2. **豐富**：後續腳本（`get_edb.py`、`set_edb.py`、`set_sim.py`、`run_sim.py` 等）分別新增所需欄位。
3. **完成**：流程結束時，`project.json` 保存所有輸入、過程資料與結果，可供重複執行或後續分析。

> 建議：新增欄位時請保持命名清晰（使用蛇形命名），並盡量讓每個腳本對欄位有單一責任，避免交叉覆蓋。

---

## 新增 App 的完整範例流程

以下以 `impedance_app` 為假想例子，示範新增流程：

1. **建立目錄結構**：
   ```text
   apps/
     impedance_app/
       __init__.py
       config.json
       controller.py
   src/tabs/
       impedance_setup_tab.py    # 若需要新的 UI Tab
   src/scripts/
       run_impedance_script.py   # 核心計算腳本
   ```

2. **撰寫 `config.json`**：
   ```json
   {
     "display_name": "Impedance Analysis",
     "description": "A flow to analyze the impedance of selected nets.",
     "tabs": {
       "import_tab": "Import",
       "impedance_setup_tab": "Setup",
       "simulation_tab": "Simulation",
       "result_tab": "Result"
     },
     "actions": {
       "impedance_setup_tab": {
         "run_impedance_script": {
           "script": "run_impedance_script.py",
           "base_dir": "src/scripts",
           "args": ["--verbose"],
           "env": {"PYAEDT_NON_GRAPHICAL": "1"}
         }
       }
     }
   }
   ```
   * `tabs` 使用物件格式時可指定顯示名稱；若使用陣列也會依序載入預設標籤名稱。
   * `actions` 可覆寫 `BaseAppController.get_action_spec()` 的預設值，包含工作目錄或環境變數。

3. **控制器 (`controller.py`)**：
   * 繼承 `BaseAppController`。
   * 在 `__init__` 中呼叫 `register_task_handlers()`，將腳本執行完成/失敗的 callback 綁定到對應事件。
   * 覆寫 `configure_tab_events()`，定義允許 UI Tabs 發佈的事件，例如 `{"impedance_setup_tab": {"impedance.run"}}`。
   * 實作 `load_config()`/`save_config()` 以保存使用者偏好（可從 `si_app` 抄寫範例）。

4. **建立新的 Tab (`impedance_setup_tab.py`)**：
   ```python
   from PySide6.QtWidgets import QVBoxLayout, QPushButton, QLineEdit, QLabel
   from .base import BaseTab

   class ImpedanceSetupTab(BaseTab):
       def __init__(self, context):
           super().__init__(context)
           layout = QVBoxLayout(self)
           self.net_input = QLineEdit()
           self.apply_button = QPushButton("Run Analysis")
           layout.addWidget(QLabel("Target Nets (comma separated)"))
           layout.addWidget(self.net_input)
           layout.addWidget(self.apply_button)

       def bind_to_controller(self):
           self.apply_button.clicked.connect(self.run_impedance_analysis)

       def run_impedance_analysis(self):
           project_file = self.controller.project_file
           if not project_file:
               self.controller.log("Please run the import step first.", "red")
               return

           nets = [s.strip() for s in self.net_input.text().split(',') if s.strip()]
           metadata = {
               "type": "run_impedance_script",
               "description": "Calculating impedance",
               "button": self.apply_button,
               "button_style": self.apply_button.styleSheet(),
               "button_reset_text": "Run Analysis"
           }

           action_spec = self.controller.get_action_spec(
               "run_impedance_script", tab_name="impedance_setup_tab"
           )
           command = [sys.executable, action_spec["script"], project_file, json.dumps({"nets": nets})]

           self.controller.submit_task(
               command,
               metadata=metadata,
               input_path=project_file,
               description=metadata["description"],
           )
   ```

5. **腳本 (`run_impedance_script.py`)**：
   ```python
   import json
   import sys

   def main(project_json_path, raw_options=None):
       with open(project_json_path, "r", encoding="utf-8") as fh:
           project = json.load(fh)

       options = json.loads(raw_options) if raw_options else {}
       nets = options.get("nets", [])

       # TODO: 使用 PyAEDT / 自訂邏輯進行計算
       results = {net: {"Z0": 50.1, "Zdiff": 99.8} for net in nets}

       project.setdefault("impedance", {})["results"] = results

       with open(project_json_path, "w", encoding="utf-8") as fh:
           json.dump(project, fh, indent=4)

   if __name__ == "__main__":
       project_file = sys.argv[1]
       options = sys.argv[2] if len(sys.argv) > 2 else None
       main(project_file, options)
   ```

6. **整合測試**：啟動 GUI，切換到 `Impedance Analysis` App，依序執行導入、設定與分析步驟，確認 `project.json` 與 UI 都正確更新。

---

## UI 與事件溝通守則

1. **TabContext 事件授權**：
   * 控制器在 `configure_tab_events()` 中指定允許發佈的事件，例如：
     ```python
     def configure_tab_events(self):
         return {
             "import_tab": {"project.project_file_created"},
             "port_setup_tab": {"ports.updated"},
             "impedance_setup_tab": {"impedance.run"}
         }
     ```
   * 若 Tab 嘗試發佈未授權事件，系統會拋出例外，協助偵錯。

2. **共享狀態**：
   * 使用 `context.update_state()` 儲存 Tab 自身狀態，`context.get_tab_state("other_tab")` 可讀取其他 Tab 的快照。
   * 需要在多個 Tab 間共用資料時，優先考慮透過事件同步，並在文件或 PR 明確說明欄位用途。

3. **GUI 元件與控制器連結**：
   * 在 Tab 的 `bind_to_controller()` 中註冊所有 UI signal，確保控制器建立後會自動綁定。
   * 呼叫長時間運行的腳本時，請使用 `context.set_button_running()`/`restore_button()` 讓使用者得到視覺回饋。

4. **日誌與錯誤訊息**：
   * 使用 `context.log("訊息", color="red")` 可同時寫入 GUI 與 `project.log`。
   * 外部腳本若寫入 stdout/stderr，`ExternalScriptRunner` 會自動轉成日誌訊號顯示在 GUI。

---

## 編寫外部腳本的最佳實務

1. **介面約定**：
   * 預設第一個參數是 `project.json` 路徑，可依需求加入額外參數（建議使用 JSON 字串或簡單旗標）。
   * 腳本應保持「無狀態」，不要依賴全域變數或上一輪執行結果。

2. **錯誤處理**：
   * 遇到錯誤時至少印出明確訊息並以非零代碼結束 (`sys.exit(1)`)，控制器會將訊息顯示在 GUI。
   * 若有可重試的情境，可在控制器呼叫 `submit_task(..., retries=<n>)`。

3. **檔案輸出**：
   * 所有輸入、輸出檔案請盡量放在 `project.json` 所在的臨時資料夾，確保流程可被複製。
   * 生成報表或模擬結果（如 Touchstone）後，記得把路徑寫回 `project.json`，讓 UI 可以自動載入。

4. **與 AEDT 互動**：
   * `pyedb.Edb` 適合處理 2.5D PCB、建立埠與堆疊。
   * `pyaedt.Hfss3dLayout` 用於驅動 SIwave/HFSS 模擬，支援 `non_graphical=True` 以減少資源需求。
   * 操作完畢務必關閉或釋放資源（例如 `edb.close_edb()`、`hfss.release_desktop()`）。

---

## 偵錯、記錄與常用工具

* **日誌檔**：控制器在提交第一個有 `input_path` 的任務時會設定 `project.log`，位置與 `project.json` 相同。建議在調試腳本時同步檢視。
* **臨時資料夾**：每次導入會在 `temp/` 下生成唯一目錄，可離線分析其中的 `project.json`、堆疊 XML、Touchstone 等。
* **Stackup Editor**：透過 GUI 的 Tools > Stackup Editor 開啟 `src/tools/stackup_editor.html`，可視覺化檢查與編輯堆疊。
* **幫助文件**：在 `apps/<app>/help.md` 撰寫說明，使用者在 GUI 中勾選 Options > Help 即可查看。
* **模組熱重新載入**：`src/gui.py` 在切換 App 時會呼叫 `importlib.invalidate_caches()` 並重新載入控制器模組，方便開發時即時看到修改結果。若修改 Tab 檔案，切換 App 後會載入最新版本。

---

## 進一步閱讀與參考資源

* 參考 `apps/si_app/` 做為完整範例：內含 `controller.py`、`config.json`、`help.md`，展示從導入、設定、模擬到報表的全流程。
* `architecture.md` 提供額外的架構概述，可與本文對照理解系統邏輯。
* `README.md` 包含專案背景與使用者導向的說明，可協助撰寫新的說明文件。
* 若需擴充 GUI 風格或功能，可參考 `src/gui.py` 的 `apply_styles()` 與 `tabs` 目錄下的各種佈局實作。

---

只要遵守上述原則，新的 App 或腳本就能與現有架構順利整合，同時維持高內聚、低耦合的設計。祝開發順利！
