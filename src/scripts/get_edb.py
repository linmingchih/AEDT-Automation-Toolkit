import sys
import os
from pyaedt import Edb
import json
from collections import defaultdict

design_path = sys.argv[1]
edb_version = sys.argv[2]
xml_path = sys.argv[3]
project_file = sys.argv[4]

print(sys.argv)
# edb_path = '../data2/Galileo_G87173_204.brd'
# edb_version = '2024.1'
# xml_path = ''

edb = Edb(design_path, edbversion=edb_version)

if xml_path:
    edb.stackup.load(xml_path)
    edb.save()

#%%
info = {}
info['component'] = defaultdict(list)
for component_name, component in edb.components.components.items():
    for pin_name, pin in component.pins.items(): 
        info['component'][component_name].append((pin_name, pin.net_name)) 

#%%
info['diff'] = {}
for differential_pair_name, differential_pair in edb.differential_pairs.items.items(): 
    pos = differential_pair.positive_net.name
    neg = differential_pair.negative_net.name
    info['diff'][differential_pair_name] = (pos, neg)
    
project_data = {}
if os.path.exists(project_file):
    with open(project_file, "r") as f:
        project_data = json.load(f)

project_data["pcb_data"] = info
project_data["ports"] = []
project_data["cct_ports_ready"] = False
project_data.pop("cct_path", None)

os.makedirs(os.path.dirname(project_file), exist_ok=True)
with open(project_file, 'w') as f:
    json.dump(project_data, f, indent=3)


edb.close_edb()
