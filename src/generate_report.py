import json
import sys

def generate_html_report(project_file):
    try:
        with open(project_file, "r") as f:
            project_data = json.load(f)

        results = project_data.get("result", {})
        if not results:
            print("No results found in project file.")
            return

        plot_data = {}
        for signal, data in results.items():
            plot_data[signal] = {
                'insertion_loss_freq': [f / 1e9 for f in data['insertion_loss']['freq']],
                'insertion_loss_val': data['insertion_loss']['insetion loss'],
                'return_loss_freq': [f / 1e9 for f in data['return_loss']['freq']],
                'return_loss_val': data['return_loss']['return loss']
            }

        # Generate sidebar items separately to avoid f-string parsing issues
        sidebar_items = ''.join([
            f'<label class="signal-item" onmouseover=\'highlightTrace({json.dumps(s)})\' onmouseout=\'unhighlightTrace()\'><input type="checkbox" name="signal" value="{s}" onchange="updatePlot()">{s}</label>' 
            for s in results.keys()
        ])

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Simulation Results</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            display: flex;
            height: 100vh;
            background-color: #f8f9fa;
        }}
        #sidebar {{
            width: 280px;
            background-color: #ffffff;
            padding: 20px;
            overflow-y: auto;
            border-right: 1px solid #dee2e6;
            box-shadow: 0 0 10px rgba(0,0,0,0.05);
        }}
        #plot-container {{
            flex-grow: 1;
            padding: 20px;
            display: flex;
            flex-direction: column;
        }}
        #plot {{
            width: 100%;
            flex-grow: 1;
        }}
        h2 {{
            font-size: 1.5em;
            color: #343a40;
            margin-top: 0;
        }}
        .signal-item {{
            display: block;
            margin-bottom: 10px;
            font-size: 1.2em;
            color: #495057;
            cursor: pointer;
            padding: 5px;
            border-radius: 4px;
        }}
        .signal-item:hover {{
            background-color: #e9ecef;
        }}
        input[type="checkbox"] {{
            margin-right: 10px;
        }}
    </style>
</head>
<body>
    <div id="sidebar">
        <hr>
        <label class="signal-item"><input type="checkbox" id="toggle-il" onchange="updatePlot()" checked>Insertion Loss</label>
        <label class="signal-item"><input type="checkbox" id="toggle-rl" onchange="updatePlot()" checked>Return Loss</label>
        <h2>Signals</h2>
        {sidebar_items}
    </div>
    <div id="plot-container">
        <div id="plot"></div>
    </div>

    <script>
        const plotData = {json.dumps(plot_data)};

        function highlightTrace(signal) {{
            const plotDiv = document.getElementById('plot');
            if (!plotDiv.data) return;

            const updates = plotDiv.data.map(trace => {{
                const isHighlighted = trace.name.startsWith(signal);
                return {{
                    line: {{ width: isHighlighted ? 4 : undefined }},
                    opacity: isHighlighted ? 1.0 : 0.3
                }};
            }});

            Plotly.restyle('plot', updates);
        }}

        function unhighlightTrace() {{
            const plotDiv = document.getElementById('plot');
            if (!plotDiv.data) return;

            const updates = plotDiv.data.map(() => ({{
                line: {{ width: undefined }},
                opacity: 1.0
            }}));
            
            Plotly.restyle('plot', updates);
        }}

        function updatePlot() {{
            const selectedSignals = Array.from(document.querySelectorAll('input[name="signal"]:checked')).map(cb => cb.value);
            const showIL = document.getElementById('toggle-il').checked;
            const showRL = document.getElementById('toggle-rl').checked;
            const traces = [];

            selectedSignals.forEach(signal => {{
                const data = plotData[signal];
                if (showIL) {{
                    traces.push({{
                        x: data.insertion_loss_freq,
                        y: data.insertion_loss_val,
                        mode: 'lines',
                        name: `${{signal}} - IL`,
                    }});
                }}
                if (showRL) {{
                    traces.push({{
                        x: data.return_loss_freq,
                        y: data.return_loss_val,
                        mode: 'lines',
                        name: `${{signal}} - RL`,
                    }});
                }}
            }});

            const layout = {{
                title: 'Signal Loss Analysis',
                xaxis: {{ title: 'Frequency (GHz)' }},
                yaxis: {{ title: 'Loss (dB)' }},
                hovermode: 'x unified',
                font: {{
                    size: 14
                }}
            }};

            Plotly.newPlot('plot', traces, layout, {{responsive: true}});
        }}

        // Initial plot
        updatePlot();
    </script>
</body>
</html>
"""
        report_path = project_file.replace("project.json", "report.html")
        with open(report_path, "w") as f:
            f.write(html_content)
        print(f"HTML report generated at: {report_path}")

    except Exception as e:
        print(f"Error generating HTML report: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        project_file = sys.argv[1]
        generate_html_report(project_file)
    else:
        print("Usage: python generate_report.py <path_to_project.json>")

