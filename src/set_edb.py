import sys
from pyaedt import Edb
import json

json_path = sys.argv[1]
edb_version = sys.argv[2]
# json_path = '../data/ports.json'

with open(json_path) as f:
    info = json.load(f)


edb = Edb(info['aedb_path'], edbversion=edb_version)
new_edb_path = info['aedb_path'].replace('.aedb', '_applied.aedb')


ref_terminals = {}
for comp_name in info['controller_components'] + info['dram_components']:
    net_name = info['reference_net']
    pgname, pg = edb.siwave.create_pin_group_on_net(comp_name, net_name, f'{comp_name}_{net_name}_ref')
    ref_terminals[comp_name] = pg.create_port_terminal(50)
    
#%%
for port in info['ports']:
    port_name = port['name']
    comp_name = port['component']
    net_name = port['net']

    pgname, pg = edb.siwave.create_pin_group_on_net(comp_name, net_name,  f'{comp_name}_{net_name}')
    terminal = pg.create_port_terminal(50)
    terminal.SetReferenceTerminal(ref_terminals[comp_name])
    terminal.SetName(port_name)

edb.save_edb_as(new_edb_path)
edb.close_edb()