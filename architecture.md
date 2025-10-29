# SI 自動化流程 – 架構總覽 (繁體中文)

## 1. 頂層結構
- **進入點 (Entry point)** – `src/main.py` 啟動一個 `QApplication` 並顯示主視窗 `MainApplicationWindow` (`src/gui.py`)。
- **應用程式外殼 (Application shell)** – `MainApplicationWindow` 負責管理：
  - 透過掃描 `apps/` 目錄下的 `<app_name>/config.json` 來**自動發現**所有可用的 App。
  - 一個動態的「應用程式」選單，用於切換不同的工作流程。
  - 一個中央的 `QTabWidget`，根據所選 App 的設定檔來載入對應的 UI 頁籤 (Tabs)。
  - 一個所有 App 共享的日誌面板 (`QTextEdit`)。
- **應用程式 (Apps)** – `apps/` 下的每個資料夾都代表一個獨立的 App，包含其設定檔 `config.json` 和控制器 `controller.py`。
- **共享 UI 頁籤 (Shared UI tabs)** – `src/tabs/` 中存放可重複使用的 PySide6 元件 (例如 `import_tab.py`, `port_setup_tab.py`)。App 透過其設定檔來決定要載入哪些頁籤。
- **共享服務 (Shared services)** – `src/services/` 中提供共享的服務，例如用於輕量級狀態儲存的 `app_state_store.py` 和用於非同步執行腳本的 `external_script_runner.py`。
- **自動化腳本 (Automation scripts)** – `src/scripts/` 中存放獨立的 Python 命令列工具，它們負責呼叫 PyAEDT / pyEDB 等函式庫來執行實際的模擬任務。

```
SI Automation Flow/
├─ apps/
│  └─ si_app/
│     ├─ config.json
│     └─ controller.py
├─ src/
│  ├─ main.py
│  ├─ gui.py
│  ├─ controllers/
│  │  └─ base_controller.py  <-- 所有控制器的基底類別
│  ├─ tabs/
│  │  ├─ import_tab.py
│  │  └─ ...
│  ├─ services/
│  │  ├─ app_state_store.py
│  │  └─ external_script_runner.py
│  └─ scripts/
│     ├─ get_edb.py
│     └─ ...
└─ temp/, requirements.txt, ...
```

## 2. 應用程式外殼 (`src/gui.py`)
- **動態 App 載入**: `discover_apps()` 掃描 `apps/` 目錄，讀取每個 App 的 `config.json`，並在選單中建立對應的選項。
- **頁籤實例化**: 當使用者透過選單切換 App 時，`switch_app()` 會匯入對應的控制器 (`apps.<app>.controller`)，將共享的日誌面板傳遞給它，並根據 App 設定檔中 `tabs` 列表的定義，實例化所有需要的 UI 頁籤。
- **控制器連接**: 在所有頁籤都建立後，`connect_signals()` 會被呼叫，讓控制器有機會連接 UI 元件的訊號 (Signal)，例如按鈕點擊事件。

## 3. App 控制器 (`src/controllers/base_controller.py` & 子類別)
此架構的核心是位於 `src/controllers/base_controller.py` 的 `BaseAppController`。**所有**在 `apps/` 目錄下的 App 控制器都必須繼承自這個基底類別。

- **`BaseAppController` 的職責**:
  - **提供共享服務**: 為所有子類別提供 `AppStateStore` (用於狀態儲存) 和 `ExternalScriptRunner` (用於任務執行) 的實例。
  - **集中化任務提交**: 提供 `_submit_task` 方法作為所有後端腳本任務的統一入口。**此方法會自動設定當前專案的 `project.json` 路徑，並初始化 `project.log` 檔案**，確保日誌記錄的即時性與準確性。
  - **集中化日誌記錄**: 提供 `log_message` 方法。此方法會**同時**將訊息發送到 GUI 的日誌面板和當前專案的 `project.log` 檔案中，實現了日誌的雙重寫入。
  - **管理任務生命週期**: 透過連接 `ExternalScriptRunner` 的訊號 (`started`, `finished`, `error`)，提供可供子類別覆寫 (override) 的標準處理函式，如 `on_task_finished` 和 `on_task_error`。

- **App 控制器子類別 (例如 `apps/si_app/controller.py`) 的職責**:
  - **實作特定邏輯**: 覆寫 `on_task_finished` 和 `on_task_error` 方法，根據完成或失敗的任務類型 (`task_type`)，執行特定的 UI 更新邏輯。例如，在 `get_edb` 任務完成後，呼叫 `port_setup_tab.load_pcb_data()` 來刷新埠設定頁籤的內容。
  - **管理 App 狀態**: 實作 `load_config` 和 `save_config` 方法，使用 `AppStateStore` 服務來載入和儲存使用者在 UI 上的設定。

## 4. UI 頁籤元件 (`src/tabs/*.py`)
每個頁籤都是一個 `QWidget` 的子類別，它封裝了特定的 UI 和互動邏輯。
- **職責**: 頁籤的主要職責是呈現 UI，並在使用者互動時 (例如點擊按鈕)，呼叫控制器提供的方法來觸發後續的業務邏輯。
- **範例 (`ImportTab`)**: `run_get_edb()` 方法會準備好執行腳本所需的參數，然後呼叫 `controller._submit_task()` 將任務交由控制器統一處理，而不是自己直接執行 `QProcess`。

## 5. 服務層 (`src/services/`)
- **`AppStateStore`**: 提供一個基於 App 名稱的鍵值對儲存機制，用於持久化使用者設定。
- **`ExternalScriptRunner`**: 維護一個任務佇列，管理 `QProcess` 的生命週期，並透過 Qt 訊號將腳本的執行狀態 (開始、結束、錯誤、日誌) 通知給控制器。這是確保 GUI 保持響應的關鍵。

## 6. 自動化腳本 (`src/scripts/`)
這些腳本是執行所有繁重工作的核心，它們被設計為完全獨立且無狀態的。
- **黃金法則**: **讀取 `project.json` -> 執行工作 -> 寫回 `project.json`**。
- **通訊**: 腳本透過兩種方式與主程式通訊：
  1.  **資料層**: 讀取和修改 `project.json` 來傳遞結構化資料。
  2.  **日誌層**: 透過 `print()` 將日誌訊息輸出到 `stdout`，`ExternalScriptRunner` 會捕捉這些訊息並透過訊號傳遞給控制器。

| 腳本 | 職責 | 輸出 |
| --- | --- | --- |
| `get_edb.py` | 導入 `.brd`/`.aedb`，提取元件/接腳/差分對等元數據 | 將 `pcb_data` 更新至 `project.json` |
| `set_edb.py` | 為指定的元件和網路建立 SIwave 埠 | 將埠設定應用於 AEDB 專案 |
| `set_sim.py` | 將 Cutout 和頻率掃描設定應用於 AEDB | 準備好可供求解的 AEDB |
| `run_sim.py` | 啟動 SIwave/HFSS 3D Layout 分析，並匯出 Touchstone 檔案 | 將 `touchstone_path` 新增至 `project.json` |
| `get_loss.py` | 使用 scikit-rf 後處理 S-參數，計算插入/回波損耗 | 將 `result` 區塊寫入 `project.json` |
| `generate_report.py` | 產生包含互動式 Plotly 圖表的 HTML 報告 | 在專案目錄下生成 `report.html` |

## 7. 資料與控制流程 (以 SI App 為例)
1.  **導入佈局 (`ImportTab` + `get_edb.py`)**:
    - 使用者在 `ImportTab` 選擇一個 `.brd` 或 `.aedb` 檔案，點擊 "Apply"。
    - `ImportTab` 呼叫 `controller._submit_task()`。
    - `BaseAppController` 的 `_submit_task` 方法**立即設定 `project.json` 的路徑並初始化 `project.log`**。
    - `ExternalScriptRunner` 執行 `get_edb.py` 腳本。
    - 腳本將 `pcb_data` 寫入 `project.json`。
    - `on_task_finished` 在 `si_app` 控制器中被觸發，它呼叫 `PortSetupTab.load_pcb_data()` 來刷新 UI。
2.  **定義埠 (`PortSetupTab` + `set_edb.py`)**:
    - 使用者在 `PortSetupTab` 中選擇元件和網路，點擊 "Apply"。
    - `PortSetupTab` 將埠的設定寫入 `project.json`，然後呼叫 `controller._submit_task()` 來執行 `set_edb.py`。
3.  **設定與執行模擬 (`SimulationTab` + `set_sim.py` + `run_sim.py`)**:
    - 使用者在 `SimulationTab` 中設定參數，點擊 "Apply"。
    - `SimulationTab` 將設定寫入 `project.json`，然後提交 `set_sim.py` 任務。
    - 在 `set_sim.py` 成功完成後，`on_task_finished` 會被觸發，並**自動觸發**下一個 `run_sim.py` 任務。
4.  **後處理與報告 (`ResultTab` + `get_loss.py` + `generate_report.py`)**:
    - 流程與上述類似，每個步驟都透過讀寫 `project.json` 來傳遞資料。

## 8. 設定與持久化
- **App 設定檔 (`apps/<app>/config.json`)**: 定義 App 的顯示名稱、描述以及需要載入的 `tabs` 順序。
- **專案檔案 (`temp/<session>/project.json`)**: 整個自動化流程的**單一事實來源 (Single Source of Truth)**，在所有腳本之間共享。
- **使用者狀態 (`%APPDATA%/si-automation-flow/<app>/state.json`)**: 儲存使用者在 UI 上的選擇，例如上次使用的 EDB 版本、頻率掃描設定等，以便下次啟動時恢復。

## 9. 擴展性指南
- **新增 App**: 參照 `developer.md` 中的詳細指南。只需建立 `apps/<new_app>` 資料夾，並在其中包含 `config.json` 和 `controller.py` 即可。
- **新增自動化步驟**: 在 `src/scripts/` 中建立新的腳本，確保它遵循讀寫 `project.json` 的原則，然後在對應的 Tab 或 Controller 中透過 `_submit_task` 呼叫它。