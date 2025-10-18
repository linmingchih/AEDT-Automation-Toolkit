import sys
import json
import skrf as rf
from collections import defaultdict
from pyaedt import Circuit

#json_path = sys.argv[1]
if len(sys.argv) > 1:
    json_path = sys.argv[1]
else:
    json_path = r"D:\OneDrive - ANSYS, Inc\a-client-repositories\lmz-siwave-SI-2025-10-17\test\project.json"

with open(json_path) as f:
    info = json.load(f)

if "touchstone_path" not in info or not info["touchstone_path"]:
    print("Error: 'touchstone_path' not found in project.json.")
    print("Please ensure the simulation has completed successfully before running post-processing.")
    sys.exit(1)

snp_path = info["touchstone_path"]

single_ended = defaultdict(lambda: ['', ''])
differential = defaultdict(lambda:[['', ''], ['', '']])

for port in info['ports']:
    if port['net_type'] == 'single':
        net_name = port['net']
        
        if port['component_role'] == 'controller':
            single_ended[net_name][0] = port['sequence']
        
        elif port['component_role'] == 'dram':
            single_ended[net_name][1] = port['sequence']

    if port['net_type'] == 'differential':
        pair_name = port['pair']
        
        if port['component_role'] == 'controller':
            if port['polarity'] == 'positive':
                differential[pair_name][0][0] = port['sequence']
            elif port['polarity'] == 'negative':
                differential[pair_name][0][1] = port['sequence']
        
        elif port['component_role'] == 'dram':
            if port['polarity'] == 'positive':
                differential[pair_name][1][0] = port['sequence']
            elif port['polarity'] == 'negative':
                differential[pair_name][1][1] = port['sequence']      
        

circuit = Circuit(version=info['solver_version'], non_graphical=False)  
model = circuit.modeler.schematic.create_touchstone_component(snp_path)

#%%
for pin in model.pins:
    circuit.modeler.schematic.create_interface_port(str(pin.pin_number), 
                                                    location=pin.location)
#%%
expressions = {}
for pair_name, (in_pair, out_pair) in differential.items():
    
    x, y = in_pair
    circuit.set_differential_pair(str(x), str(y), differential_mode=f'Diff1_{pair_name}')
    
    x, y = out_pair
    circuit.set_differential_pair(str(x), str(y), differential_mode=f'Diff2_{pair_name}')
    
    expressions[pair_name] = (f'dB(S(Diff1_{pair_name},Diff1_{pair_name}))',
                              f'dB(S(Diff2_{pair_name},Diff1_{pair_name}))')

for net_name, (_in, _out) in single_ended.items():
    expressions[net_name] = (f'dB(S({_in},{_in}))', f'dB(S({_out},{_in}))')
    
ntwk = rf.Network(snp_path)
     
setup = circuit.create_setup()
setup.add_sweep_points(sweep_points=ntwk.frequency.f, units='Hz')
setup.analyze()

#%%
result = {}
for name, (expression1, expression2) in expressions.items():
    data = circuit.post.get_solution_data(expression1, context="Differential Pairs")
    x1 = data.primary_sweep_values
    y1 = data.data_real()
    
    data = circuit.post.get_solution_data(expression2, context="Differential Pairs")
    x2 = data.primary_sweep_values
    y2 = data.data_real()
    
    result[name] = {'return_loss': {'freq':list(x1), 'return loss':list(y1)},
                    'insertion_loss': {'freq':list(x2), 'insetion loss':list(y2)}
                    }
circuit.release_desktop()

info['result'] = result

with open(json_path, 'w') as f:
    json.dump(info, f)