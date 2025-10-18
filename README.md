# SI 自動化模擬工具

這是一個用於訊號完整性 (SI) 模擬的自動化工具，提供圖形化使用者介面 (GUI) 來簡化從設計導入到結果分析的整個流程。

## 主要功能

- **設計導入**: 支援 Ansys EDB (`.aedb`) 和 Cadence Allegro (`.brd`) 設計檔案。
- **圖形化設定**: 提供方便的介面來設定元件、網路和埠。
- **自動化模擬**: 自動設定並執行 SIwave 模擬。
- **損耗計算**: 自動計算所選網路的插入損耗 (Insertion Loss) 和回波損耗 (Return Loss)。
- **互動式報告**: 生成一個獨立的 HTML 報告，您可以在其中：
  - 透過側邊欄的複選框，動態選擇要顯示的多個訊號。
  - 在同一個圖表中比較不同訊號的損耗曲線。
  - 將滑鼠懸停在側邊欄的訊號名稱上，可以高亮顯示圖表中對應的曲線。
  - 自由切換顯示插入損耗或回波損耗。

![應用程式介面](images/GUI.png)

## 系統需求

- Python 3.10+
- Ansys Electronics Desktop (需包含 SIwave 功能)

## 安裝說明

1.  **克隆專案庫**
    ```bash
    git clone <repository_url>
    ```

2.  **安裝依賴套件**
    執行 `install.ps1` PowerShell 腳本。此腳本將會自動建立一個 Python 虛擬環境 (`.venv`) 並安裝所有必要的依賴套件。
    ```powershell
    .\install.ps1
    ```

## 使用方法

1.  **啟動應用程式**
    執行 `main.bat` 批次檔來啟動 GUI。
    ```batch
    .\main.bat
    ```

2.  **第一步：導入設計 (Import Tab)**
    - 選擇您的設計類型 (`.brd` 或 `.aedb`)。
    - 點擊 "Open..." 選擇您的設計檔案。如果導入的是 `.brd` 檔案，您還可以額外指定一個堆疊設定檔 (`.xml`)。
    - 確認 Ansys EDB 版本。
    - 點擊 "Apply" 開始導入。導入成功後，應用程式會自動切換到 "Port Setup" 分頁。

3.  **第二步：設定埠 (Port Setup Tab)**
    - 使用正則表達式過濾並在左右兩側的列表中分別選擇控制器 (Controller) 和 DRAM 元件。
    - 在下方的網路列表中，勾選您想要分析的單端 (Single-Ended) 和差動 (Differential) 網路。
    - 點擊 "Apply" 將埠設定應用到 EDB 專案中。

4.  **第三步：執行模擬 (Simulation Tab)**
    - 根據需求配置 SIwave 求解器版本和頻率掃描範圍。
    - 點擊 "Apply" 開始執行模擬。此過程可能需要一些時間。

5.  **第四步：查看結果 (Result Tab)**
    - 模擬成功後，`project.json` 的檔案路徑會被自動填入此處。您也可以點擊 "Browse..." 手動指定。
    - 點擊 "Apply" 來計算損耗參數並生成互動式的 HTML 報告。報告將會儲存在與 `project.json` 相同的資料夾下。

![互動式報告](images/report.png)
