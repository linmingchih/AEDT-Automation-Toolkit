import sys
from pyaedt import Edb
import json
from collections import defaultdict

design_path = sys.argv[1]
edb_version = sys.argv[2]
xml_path = sys.argv[3]

print(sys.argv)
# edb_path = '../data2/Galileo_G87173_204.brd'
# edb_version = '2024.1'
# xml_path = ''

if '.aedb' in design_path:
    json_path = design_path.replace('.aedb', '.json')
if '.brd' in design_path:
    json_path = design_path.replace('.brd', '.json')
    
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
    
with open(json_path, 'w') as f:
    json.dump(info, f, indent=3)


edb.close_edb()