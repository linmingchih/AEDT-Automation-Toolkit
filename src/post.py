import os
import sys
import webbrowser
import json
import skrf as rf
import numpy as np

def process_simulation_data(project_file):
    """
    Processes a large Touchstone file based on port mappings in a project.json file.
    """
    plot_data = []
    
    try:
        with open(project_file, 'r') as f:
            config = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing project file: {e}")
        return []

    touchstone_path = config.get("touchstone_path")
    ports = config.get("ports", [])

    if not touchstone_path or not os.path.exists(touchstone_path):
        print(f"Touchstone file not found at path: {touchstone_path}")
        return []

    try:
        network = rf.Network(touchstone_path)
    except Exception as e:
        print(f"Error reading Touchstone file {touchstone_path}: {e}")
        return []

    # Group ports by net or pair name
    net_groups = {}
    for i, port in enumerate(ports):
        # Port indices in skrf are 0-based, port sequence in json is 1-based
        port_index = i
        
        key = port.get("pair") if port.get("net_type") == "differential" else port.get("net")
        if key not in net_groups:
            net_groups[key] = []
        net_groups[key].append({
            "port_index": port_index,
            "component": port.get("component_role"),
            "polarity": port.get("polarity")
        })

    # Process each group
    for name, group_ports in net_groups.items():
        try:
            # --- Process Single-Ended Nets ---
            if len(group_ports) == 2:
                p1, p2 = group_ports[0]["port_index"], group_ports[1]["port_index"]
                
                # S21 is insertion loss, S11 is return loss
                sub_network = network.subnetwork([p1, p2])
                
                plot_data.append({
                    "name": name,
                    "type": "single_ended",
                    "frequency": sub_network.f.tolist(),
                    "il": sub_network.s_db[:, 1, 0].tolist(), # S21
                    "rl": sub_network.s_db[:, 0, 0].tolist()  # S11
                })

            # --- Process Differential Pairs ---
            elif len(group_ports) == 4:
                # Order ports correctly: [p1_pos, p1_neg, p2_pos, p2_neg]
                # This is crucial for correct mixed-mode conversion.
                port_map = {}
                for p in group_ports:
                    key = f"{p['component']}_{p['polarity']}"
                    port_map[key] = p['port_index']
                
                # Assuming two components, e.g., 'controller' and 'dram'
                comps = sorted(list(set(p['component'] for p in group_ports)))
                if len(comps) != 2: continue

                ordered_indices = [
                    port_map[f"{comps[0]}_positive"], port_map[f"{comps[0]}_negative"],
                    port_map[f"{comps[1]}_positive"], port_map[f"{comps[1]}_negative"]
                ]

                sub_network = network.subnetwork(ordered_indices)
                se2mm = sub_network.se2gmm(p=2) # 2 differential ports
                
                plot_data.append({
                    "name": name,
                    "type": "differential",
                    "frequency": se2mm.f.tolist(),
                    "il": se2mm.s_db[:, 1, 0].tolist(), # Sdd21
                    "rl": se2mm.s_db[:, 0, 0].tolist()  # Sdd11
                })
        except Exception as e:
            print(f"Failed to process net '{name}': {e}")

    return plot_data

def create_html_report(data, project_dir):
    """
    Generates an interactive HTML report with S-parameter plots using Plotly.js.
    """
    json_data = json.dumps(data, indent=4)
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>S-Parameter Simulation Results</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 2em; background-color: #f8f9fa; }}
        h1 {{ color: #343a40; }}
        .controls {{ margin-bottom: 1.5em; background-color: #fff; padding: 1em; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        label {{ margin-right: 0.5em; }}
        input[type="number"] {{ padding: 5px; border: 1px solid #ced4da; border-radius: 4px; }}
        .plot-container {{ display: flex; flex-wrap: wrap; gap: 1em; }}
        .plot {{ width: calc(50% - 1em); background-color: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    </style>
</head>
<body>
    <h1>S-Parameter Simulation Results</h1>
    <div class="controls">
        <label for="rows">Number of nets to display:</label>
        <input type="number" id="rows" value="10" min="1" onchange="renderPlots()">
    </div>
    <div id="plots-container" class="plot-container"></div>

    <script>
        const simData = {json_data};

        function renderPlots() {{
            const container = document.getElementById('plots-container');
            container.innerHTML = '';
            const rowsToShow = parseInt(document.getElementById('rows').value, 10);

            const dataToShow = simData.slice(0, rowsToShow);

            dataToShow.forEach(netData => {{
                const ilDiv = document.createElement('div');
                ilDiv.className = 'plot';
                const rlDiv = document.createElement('div');
                rlDiv.className = 'plot';
                
                container.appendChild(ilDiv);
                container.appendChild(rlDiv);

                const ilTrace = {{
                    x: netData.frequency,
                    y: netData.il,
                    mode: 'lines',
                    name: 'Insertion Loss'
                }};
                const ilLayout = {{
                    title: `<b>${{netData.name}}</b><br>Insertion Loss (${{netData.type}})`,
                    xaxis: {{ title: 'Frequency (Hz)' }},
                    yaxis: {{ title: 'Magnitude (dB)' }},
                    margin: {{ t: 60, b: 40, l: 50, r: 20 }}
                }};
                Plotly.newPlot(ilDiv, [ilTrace], ilLayout);

                const rlTrace = {{
                    x: netData.frequency,
                    y: netData.rl,
                    mode: 'lines',
                    name: 'Return Loss',
                    marker: {{ color: 'orange' }}
                }};
                const rlLayout = {{
                    title: `<b>${{netData.name}}</b><br>Return Loss (${{netData.type}})`,
                    xaxis: {{ title: 'Frequency (Hz)' }},
                    yaxis: {{ title: 'Magnitude (dB)' }},
                    margin: {{ t: 60, b: 40, l: 50, r: 20 }}
                }};
                Plotly.newPlot(rlDiv, [rlTrace], rlLayout);
            }});
        }}

        document.addEventListener('DOMContentLoaded', renderPlots);
    </script>
</body>
</html>
"""
    
    file_path = os.path.join(project_dir, 'result.html')
    with open(file_path, 'w') as f:
        f.write(html_content)
    
    return file_path

def main():
    """Main function to generate and open the report."""
    if len(sys.argv) < 2:
        print("Usage: python post.py <path_to_project.json>")
        return

    project_file = sys.argv[1]
    project_dir = os.path.dirname(project_file)
    
    simulation_data = process_simulation_data(project_file)
    
    if not simulation_data:
        print("No data processed. No report generated.")
        return
        
    report_path = create_html_report(simulation_data, project_dir)
    
    webbrowser.open(f"file://{os.path.realpath(report_path)}")
    print(f"Successfully generated and opened {report_path}")

if __name__ == "__main__":
    main()
