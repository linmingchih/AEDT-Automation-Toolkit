import sys
import json

#json_path = '../data/simulation.json'
json_path = sys.argv[1]

with open(json_path) as f:
    info = json.load(f)

from pyedb import Edb, Siwave
edb_path = info['aedb_path'].replace('.aedb', '_applied.aedb')
edb = Edb(edb_path, version=info['edb_version'])

if info['cutout']['enabled']:
    edb.cutout(signal_nets=info['cutout']['signal_nets'],
               reference_nets=info['cutout']['reference_net'],
               expansion_size=float(info['cutout']['expansion_size'])
               )
    
if info['solver'] == 'SIwave':
    setup = edb.create_siwave_syz_setup()
    setup.add_frequency_sweep(frequency_sweep=info['frequency_sweeps'])

elif info['solver'] == 'HFSS':
    setup = edb.create_hfss_setup()
    sweep = setup.add_sweep(frequency_set=info['frequency_sweeps'][0])
    for i in info['frequency_sweeps'][1:]:
        sweep.add(*i)


edb.save()
edb.close_edb()

    
    