# SI Automation Flow – Architecture Overview

## 1. Top-Level Structure
- **Entry point –** `src/main.py` boots a `QApplication` and shows `MainApplicationWindow` (`src/gui.py`).
- **Application shell –** `MainApplicationWindow` manages:
  - discovery of apps under `apps/` by inspecting each `<app_name>/config.json` and `<app_name>/controller.py`,
  - a dynamic “Apps” menu for switching flows,
  - a central `QTabWidget` populated by the selected app’s tabs (`tabs/…`),
  - a shared log pane (`QTextEdit`) exposed to controllers as `log_window`.
- **Apps –** each folder in `apps/` holds an app-specific `config.json` and `controller.py`. For example, `apps/si_app/controller.py` defines the signal-integrity automation flow.
- **Shared UI tabs –** reusable PySide6 widgets in `src/tabs/` (e.g., `import_tab.py`, `port_setup_tab.py`). An app chooses which tabs to load via its config.
- **Shared services –** `src/services/app_state_store.py` for lightweight persistence, `src/services/external_script_runner.py` for queued execution of helper scripts.
- **Automation scripts –** Python command-line utilities in `src/scripts/` (e.g., `get_edb.py`, `set_edb.py`) that call PyAEDT / pyEDB tooling. They run outside the GUI and communicate via JSON files and stdout.

```
SI Automation Flow/
├─ apps/
│  └─ si_app/
│     ├─ config.json
│     └─ controller.py
├─ src/
│  ├─ main.py
│  ├─ gui.py
│  ├─ tabs/
│  │  ├─ import_tab.py
│  │  ├─ port_setup_tab.py
│  │  ├─ simulation_tab.py
│  │  └─ result_tab.py
│  ├─ services/
│  │  ├─ app_state_store.py
│  │  └─ external_script_runner.py
│  └─ scripts/
│     ├─ get_edb.py
│     ├─ set_edb.py
│     ├─ set_sim.py
│     ├─ run_sim.py
│     ├─ get_loss.py
│     └─ generate_report.py
└─ images/, temp/, requirements.txt, ...
```

## 2. Application Shell (`src/gui.py`)
- **Dynamic app loading.** `discover_apps()` scans `apps/`, reads each config, and creates menu actions that call `switch_app(app_name)`.
- **Tab instantiation.** `switch_app` imports `apps.<app>.controller`, instantiates `AppController(app_name)`, gives it the shared log widget, and loads each tab listed in the app config. Tabs are created from `src/tabs` modules by deriving the class name from the module name (e.g., `port_setup_tab` → `PortSetupTab`).
- **Controller wiring.** After all tabs are instantiated, `connect_signals(tabs)` (if present) lets the controller cache tab references and hook orchestrated behaviour.
- **Lifecycle.** On close, `save_config()` is called on the active controller (if implemented), enabling app-defined persistence.

## 3. SI App Controller (`apps/si_app/controller.py`)
- **Responsibilities.**
  - Maintains shared state for the flow: project JSON path, in-memory PCB data, references to tab widgets, app-wide services (`AppStateStore`, `ExternalScriptRunner`).
  - Coordinates long-running tasks by delegating to `ExternalScriptRunner` and reacting to its signals (`started`, `finished`, `error`, `log_message`).
  - Persists user choices (`save_config`) and restores them when the app loads (`load_config`).
  - Provides utility helpers for tabs: centralised logging, button state management, and submission of background tasks (`_submit_task`).
- **Signal binding.** After refactoring, `connect_signals` simply calls `bind_to_controller()` on each tab. Tabs now own their UI event handlers and call back into the controller for orchestration.
- **Task lifecycle handling.**
  - On success (`on_task_finished`): updates UI state (e.g., new AEDB path after import, repopulating Port Setup data, triggering next stage like running the report).
  - On failure (`on_task_error`): restores button styles, hides result panels, and writes log messages.
  - On log messages (`on_task_log_message`): streams script stdout/stderr into the shared log window and captures metadata such as generated report paths.
- **Persistence.**
  - `AppStateStore` keeps per-app JSON under `%APPDATA%\si-automation-flow\<app>\state.json` (Windows) or platform equivalents.
  - `save_config` serialises simulation defaults (cutout, sweeps) and the last project file. It also patches the active project JSON with app metadata when available.
  - `load_config` hydrates tabs with stored defaults and ensures the Result tab reflects the current project file.

## 4. Tab Components (`src/tabs/*.py`)
Each tab is a `QWidget` subclass that accepts the controller instance. Tabs encapsulate UI behaviour and interaction logic while using controller services for cross-cutting concerns.

### 4.1 ImportTab (`src/tabs/import_tab.py`)
- UI for selecting a layout source (.brd or .aedb), optional stack-up XML, and the target EDB version.
- `bind_to_controller` wires button clicks and radio toggles to methods living on the tab itself.
- `run_get_edb()` prepares an isolated session directory under `<project_root>/temp/<design>_<timestamp>/`, copies the selected layout/stackup, records the future project JSON path, and schedules `src/scripts/get_edb.py` through the controller.
- On completion, `AppController` updates the layout label and triggers `PortSetupTab.load_pcb_data()` to refresh component data.

### 4.2 PortSetupTab (`src/tabs/port_setup_tab.py`)
- Manages component filtering, controller/DRAM selection, net discovery, and port definition.
- Maintains a cached list of components (`self.all_components`) populated when `load_pcb_data()` parses the project JSON produced by `get_edb.py`.
- `update_nets()` derives common nets between the selected controller and DRAM parts, populates single-ended and differential lists, and keeps the reference net combo in sync.
- `apply_settings()` serialises the selected ports, nets, and reference into the project JSON, mirrors that info into the Simulation tab (signal/reference labels), and submits `set_edb.py` to generate SIwave ports.
- Uses controller helpers to show progress (disabling Apply buttons, logging) and to enqueue scripts.

### 4.3 SimulationTab (`src/tabs/simulation_tab.py`)
- Hosts cutout controls, solver version, and a sweep table with add/remove operations.
- `apply_simulation_settings()` validates prerequisites (e.g., Port Setup must define nets), writes sweep/cutout settings into the project JSON, and fires `set_sim.py`. Upon completion, the controller automatically schedules the full SIwave run (`run_sim.py`).

### 4.4 ResultTab (`src/tabs/result_tab.py`)
- Handles post-processing: choosing an existing project JSON, invoking loss extraction (`get_loss.py`), and generating an HTML report (`generate_report.py`).
- `run_post_processing()` resets the HTML group visibility, locks the Apply button, and triggers `run_get_loss()`; success cascades into `run_generate_report()`, after which the controller re-enables the UI and exposes the report path textbox plus “Open” button.
- `open_report_in_browser()` opens the generated HTML using the default browser and logs the action.

## 5. Services Layer

### 5.1 AppStateStore (`src/services/app_state_store.py`)
- Provides a key/value persistence mechanism for each named app.
- Encapsulates OS-specific paths (AppData / Application Support / `~/.config`).
- Offers `load(app_name) -> dict` and `save(app_name, data)`; callers handle schema evolution by reading, mutating, and writing JSON dictionaries.

### 5.2 ExternalScriptRunner (`src/services/external_script_runner.py`)
- Queues external commands (typically Python scripts) and keeps at most `max_concurrent` `QProcess` instances alive.
- Emits Qt signals consumed by `AppController` to follow script progress.
- Supports retries, cancellation, logging of stdout/stderr, and blocking vs. asynchronous execution models.
- Centralises error handling so tabs do not manage `QProcess` lifecycles directly.

## 6. Automation Scripts (`src/scripts/`)
Scripts perform compute-heavy or licensed tasks using PyAEDT/pyEDB APIs, keeping the GUI responsive.

| Script | Responsibility | Output |
| -- | -- | -- |
| `get_edb.py` | Imports `.brd`/`.aedb` into EDB, loads optional stackup XML, extracts component/pin/differential-pair metadata | Updates `project.json` with `pcb_data` |
| `set_edb.py` | Builds SIwave pin groups and ports for selected components/nets | Applies ports in-place to the AEDB |
| `set_sim.py` | Applies cutout settings and frequency sweeps to the AEDB | AEDB ready for SIwave solve |
| `run_sim.py` | Launches SIwave/HFSS 3D Layout analysis, exports Touchstone | Appends `touchstone_path` to `project.json` |
| `get_loss.py` | Post-processes S-parameters, computes insertion/return loss using scikit-rf & Circuit | Writes `result` section in `project.json` |
| `generate_report.py` | Renders interactive Plotly HTML summarising loss metrics | `report.html` alongside the project JSON |

Scripts communicate through the shared `project.json`, so each stage enriches the dataset for the next step. The controller metadata ties script runs back to initiating buttons for UI feedback.

## 7. Data & Control Flow (SI App)
1. **Import layout (ImportTab + `get_edb.py`).**
   - User selects `.brd` or `.aedb`; the tab creates an isolated working folder, copies inputs, then spawns `get_edb.py`.
   - Script extracts `pcb_data` (components, nets, diff pairs) and writes it into `project.json`.
   - Controller loads the enriched JSON and calls `PortSetupTab.load_pcb_data()` to populate UI lists.
2. **Define ports (PortSetupTab + `set_edb.py`).**
   - User filters/selects components, checks nets/pairs. Tab builds `ports` array and writes simulation metadata, including signal/reference nets, into `project.json`.
   - Tab updates Simulation tab labels to mirror the selected nets.
   - `set_edb.py` consumes the JSON to add SIwave ports in the AEDB.
3. **Configure simulation (SimulationTab + `set_sim.py` + `run_sim.py`).**
   - User edits cutout and sweep definitions. Tab writes them into the JSON and triggers `set_sim.py`.
   - On success, controller queues `run_sim.py`, which drives SIwave/HFSS to produce a Touchstone file and records its path.
4. **Post-process & report (ResultTab + `get_loss.py` + `generate_report.py`).**
   - User points to the project JSON (auto-filled after simulation). Tab runs `get_loss.py`, which calculates loss metrics based on the Touchstone file and updates the JSON.
   - Controller initiates `generate_report.py`, producing `report.html` with Plotly plots. UI reveals the HTML section and allows the user to open it.
5. **Logging & feedback.**
   - Throughout, stdout/stderr from scripts is streamed into the shared log pane. Buttons are disabled/enabled automatically to avoid duplicate submissions.

## 8. Configuration & Persistence
- **App config (`apps/<app>/config.json`).** Declares display name, tab order, and optional defaults. Example (SI app):
  ```json
  {
    "display_name": "SI Automation Flow",
    "tabs": [
      "import_tab",
      "port_setup_tab",
      "simulation_tab",
      "result_tab"
    ]
  }
  ```
- **Project file (`temp/<session>/project.json`).** Central data contract shared by all scripts; contains fields such as `app_name`, `aedb_path`, `pcb_data`, `ports`, `frequency_sweeps`, `touchstone_path`, and `result`.
- **User state (`%APPDATA%/si-automation-flow/<app>/state.json`).** Stores last-used values for EDB version, cutout settings, sweep definitions, etc. `AppController` reads on load and writes on exit.

## 9. Extensibility Guidelines
- **Adding new apps.** Create `apps/<new_app>/config.json` + `controller.py`, reuse existing tabs or build new ones under `src/tabs/`. The GUI auto-discovers the app.
- **Sharing tabs.** Tabs are designed to be generic; they rely solely on controller methods/services. To customise behaviour, extend the tab class or supply additional methods on the controller that the tab can call.
- **Introducing new automation steps.** Implement a script under `src/scripts/`, then submit it via `ExternalScriptRunner` with metadata describing the initiating button and log messages. Ensure the script reads/writes the `project.json` or other agreed artefacts.
- **Handling new data.** Expand the project JSON schema carefully; tabs and scripts should tolerate missing keys by providing defaults. Persist user preferences through `AppStateStore` when they need to survive app restarts.

## 10. External Dependencies
- **PySide6** – GUI toolkit for main window, tabs, and signals/slots.
- **PyAEDT / pyEDB / SIwave APIs** – automate layout import, port setup, cutouts, and electromagnetic solves.
- **scikit-rf** – post-process Touchstone files for loss metrics.
- **Plotly (CDN)** – interactive HTML reporting.
- **UUID / subprocess / QProcess** – used by `ExternalScriptRunner` to manage external jobs.

The combination of a Qt front-end, a task runner, and script-based heavy lifting keeps the UI responsive while leveraging vendor toolchains for simulation. Tabs operate as independent, testable units that interact with the controller through well-defined hooks, enabling the project to scale to additional flows without altering the application shell.
