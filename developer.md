### 新增 App 開發者指南

歡迎來到 SI/PI 自動化平台！這個框架的核心設計理念是**可擴展性**。你可以把主程式 (`src/gui.py`) 想像成一個「遊戲主機」，而我們要新增的各個 App (如 `si_app`, `cct`) 就像是可插拔的「遊戲卡帶」。你只需要依照規則製作你的卡帶，主機就能自動識別並運行它，完全不需要修改主機本身。

#### 一、核心理念：三層分離與資料流

要理解這個框架，首先要掌握三個核心概念：

1.  **UI 層 (Tabs)**：位於 `src/tabs/`。這些是可重複使用的 PyQt 元件，像是「導入面板」、「埠設定面板」。它們只負責顯示資訊和接收使用者的點擊，是「啞的 (Dumb)」元件。

2.  **控制層 (Controller)**：位於 `apps/<你的App>/controller.py`。這是你的 App 的「大腦」。它負責：
    *   告訴主程式要載入哪些 UI Tabs。
    *   回應使用者在 UI 上的操作 (例如，點擊「Apply」按鈕)。
    *   呼叫後端的自動化腳本來執行真正的任務。
    *   根據腳本的執行結果，更新 UI 顯示。

3.  **腳本層 (Scripts)**：位於 `src/scripts/`。這些是獨立的 Python 腳本，負責執行所有繁重的工作 (例如，呼叫 PyAEDT、分析資料)。它們的設計原則是：
    *   **無狀態 (Stateless)**：腳本自身不保存任何狀態。
    *   **單一入口**：所有需要的資訊都從一個名為 `project.json` 的檔案讀取。
    *   **單一出口**：所有執行的結果都寫回到同一個 `project.json` 檔案中。

**最重要的概念：`project.json` 的生命週期**

整個自動化流程的靈魂是 `project.json` 檔案。它就像一個在工廠流水線上傳遞的「工作清單」。

1.  **建立**：流程開始時 (通常在 `ImportTab`)，系統會在 `temp/` 目錄下建立一個專案資料夾，並在其中生成一個初始的 `project.json`。
2.  **傳遞與豐富**：
    *   控制器呼叫第一個腳本 (`get_edb.py`)，並將 `project.json` 的路徑傳給它。
    *   `get_edb.py` 讀取 `project.json`，執行 EDB 導入，然後將 PCB 的元件、網路等資訊寫回 `project.json`。
    *   控制器收到完成訊號後，呼叫下一個腳本 (`set_edb.py`)，再次傳入同一個 `project.json` 的路徑。
    *   `set_edb.py` 讀取 `project.json` 中已有的 PCB 資訊和使用者設定的埠資訊，在 EDB 中建立埠，然後將執行的結果再次寫回 `project.json`。
3.  **完成**：流程結束時，`project.json` 中包含了這次執行的所有輸入參數、中間資料和最終結果。

> **給開發者的啟示**：你寫的任何新腳本，都必須遵循「**讀取 `project.json` -> 執行工作 -> 寫回 `project.json`**」這個黃金法則。

#### 二、實戰：新增一個 App 的步驟

假設我們要新增一個名為 `impedance_app` 的阻抗分析 App。

**步驟 1：建立 App 基本結構**

1.  在 `apps/` 目錄下，建立一個新的資料夾 `impedance_app`。
2.  在 `apps/impedance_app/` 中，建立兩個檔案：`config.json` 和 `controller.py`。

**步驟 2：撰寫 `config.json`**

這個檔案是你的 App 的「名片」，主程式會讀取它來了解你的 App。

```json
{
  "display_name": "Impedance Analysis",
  "description": "A flow to analyze the impedance of selected nets.",
  "tabs": [
    "import_tab",
    "impedance_setup_tab", 
    "simulation_tab",
    "result_tab"
  ]
}
```
*   `display_name`: 顯示在 GUI 下拉選單中的名稱。
*   `description`: 你的 App 的簡短描述。
*   `tabs`: 一個列表，定義了你的 App 需要哪些 UI 介面，以及它們的**顯示順序**。這裡我們假設需要一個新的 `impedance_setup_tab`。

**步驟 3：(可選) 建立新的 UI Tab**

如果現有的 Tabs 不夠用，你可以在 `src/tabs/` 中建立一個新的檔案，例如 `impedance_setup_tab.py`。

*   這個檔案需要包含一個繼承自 `QWidget` 的類別，例如 `ImpedanceSetupTab`。
*   在這個類別中，你可以用 PyQt 建立任何你需要的 UI 元件 (輸入框、按鈕等)。
*   最重要的是，要有一個 `bind_to_controller` 方法，用來將按鈕的 `clicked` 事件連接到你在 Tab 中定義的處理函式 (例如 `self.run_impedance_analysis`)。

**步驟 4：撰寫 `controller.py`**

這是你的 App 的核心。你需要建立一個繼承自 `BaseAppController` 的 `AppController` 類別。

```python
# apps/impedance_app/controller.py
import os
from src.controllers.base_controller import BaseAppController

class AppController(BaseAppController):
    def __init__(self, app_name):
        super().__init__(app_name)

    def get_config_path(self):
        # 讓控制器能找到自己的設定檔
        return os.path.join(os.path.dirname(__file__), "config.json")

    def on_task_finished(self, task_id, exit_code, metadata):
        # 處理來自後端腳本的完成訊號
        super().on_task_finished(task_id, exit_code, metadata) # 可選，用於恢復按鈕狀態
        
        task_type = metadata.get("type")

        if task_type == "get_edb":
            # get_edb 是通用的，處理邏輯可以從 si_app 複製過來
            self.log("Layout imported successfully.")
            port_setup_tab = self.tabs.get("port_setup_tab") # 如果你用了這個 tab
            if port_setup_tab:
                port_setup_tab.load_pcb_data()
        
        elif task_type == "run_impedance_script":
            # 這是我們這個 App 特有的任務
            self.log("Impedance analysis finished.")
            # 在這裡可以觸發下一步，例如自動跳到 Result Tab
            result_tab = self.tabs.get("result_tab")
            if result_tab:
                result_tab.project_path_input.setText(self.project_file)

    def on_task_error(self, task_id, exit_code, message, metadata):
        # 處理錯誤，可以從 si_app 複製過來並修改
        pass

    def load_config(self):
        # 載入 App 狀態，例如使用者上次輸入的參數
        pass

    def save_config(self):
        # 儲存 App 狀態
        pass
```

**步驟 5：撰寫你的自動化腳本**

在 `src/scripts/` 中，建立你的核心邏輯腳本，例如 `run_impedance_script.py`。

```python
# src/scripts/run_impedance_script.py
import sys
import json

def main(project_json_path):
    # 1. 讀取 project.json
    with open(project_json_path, 'r') as f:
        project_data = json.load(f)

    # 2. 執行你的核心工作
    #    從 project_data 中獲取需要的參數 (例如 aedb_path, selected_nets)
    #    使用 PyAEDT 或其他工具進行阻抗計算
    print("Starting impedance calculation...")
    impedance_results = {"Z0": 50.1, "Zdiff": 99.8} # 假設的結果
    print("Calculation complete.")

    # 3. 將結果寫回 project.json
    project_data["impedance_results"] = impedance_results
    with open(project_json_path, 'w') as f:
        json.dump(project_data, f, indent=4)

if __name__ == "__main__":
    project_file = sys.argv[1]
    main(project_file)
```

**步驟 6：將所有部分連接起來**

最後，在你自訂的 `impedance_setup_tab.py` 中，當使用者點擊「Apply」時，你需要呼叫控制器的方法來提交任務。

```python
# 在 ImpedanceSetupTab 類別中
def run_impedance_analysis(self):
    # ... 準備 command 和 metadata ...
    
    # 透過 self.controller 呼叫基底控制器提供的通用方法
    self.controller._submit_task(
        command,
        metadata=metadata,
        input_path=self.controller.project_file # 關鍵！傳入 project.json
    )
```

---

#### 三、最佳實踐

*   **保持腳本的純粹性**：不要在 `src/scripts/` 的腳本中包含任何 UI 相關的邏輯。它們只應該關心資料的輸入和輸出。
*   **複用現有元件**：在建立新的 Tab 之前，先看看 `src/tabs/` 中是否有可以複用的。
*   **善用日誌**：在你的控制器和 Tab 邏輯中，多使用 `self.controller.log("message")`，這會將訊息同時輸出到 GUI 和 `project.log`，對於除錯非常有幫助。
*   **不要害怕參考**：`apps/si_app/` 是一個功能最完整的範例，當你不確定如何實作時，就去參考它的 `controller.py` 和 `config.json`。

只要遵循以上步驟和原則，你就可以輕鬆地為這個平台添加任何你想要的新功能，而不會破壞現有的架構。
