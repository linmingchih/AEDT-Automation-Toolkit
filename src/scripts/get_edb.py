import sys
import os
import json
from collections import defaultdict
from pyedb import Edb

# Expects a single argument: the path to the project.json file
if len(sys.argv) != 2:
    print("Usage: python get_edb.py <project_file_path>")
    sys.exit(1)

project_file = sys.argv[1]

if not os.path.exists(project_file):
    print(f"Error: Project file not found at {project_file}")
    sys.exit(1)

try:
    with open(project_file, "r") as f:
        project_data = json.load(f)
except json.JSONDecodeError:
    print(f"Error: Could not decode JSON from {project_file}")
    sys.exit(1)

# Read parameters from the JSON file
design_path = project_data.get("aedb_path")
edb_version = project_data.get("edb_version")
input_xml_path = project_data.get("stackup_path")

if not design_path:
    print("Error: 'aedb_path' not found in project file.")
    sys.exit(1)

print(f"Processing design: {design_path}")
if edb_version:
    print(f"Using EDB version: {edb_version}")
if input_xml_path:
    print(f"Using stackup file: {input_xml_path}")

edb = Edb(design_path, version=edb_version)

if input_xml_path:
    edb.stackup.load(input_xml_path)
    edb.save()

# Export the stackup from EDB to a new XML file
exported_xml_path = edb.edbpath.replace('.aedb', '.xml')
edb.stackup.export(exported_xml_path)

# Extract component and differential pair information
info = {}
info['component'] = defaultdict(list)
for component_name, component in edb.components.components.items():
    for pin_name, pin in component.pins.items():
        info['component'][component_name].append((pin_name, pin.net_name))

info['diff'] = {}
for dp_name, dp in edb.differential_pairs.items.items():
    pos_net = dp.positive_net.name
    neg_net = dp.negative_net.name
    info['diff'][dp_name] = (pos_net, neg_net)

# Update the project data dictionary
if design_path.lower().endswith(".brd"):
    project_data["aedb_path"] = edb.edbpath
project_data['xml_path'] = exported_xml_path
project_data["pcb_data"] = info
project_data["ports"] = []
project_data["cct_ports_ready"] = False
project_data.pop("cct_path", None)

# Write the updated data back to the project file
with open(project_file, 'w') as f:
    json.dump(project_data, f, indent=4)

edb.close_edb()

print(f"Successfully processed EDB and updated {project_file}")
