import sys
import json


project_file = sys.argv[1]
#project_file = r"D:\OneDrive - ANSYS, Inc\a-client-repositories\lmz-siwave-SI-2025-10-17\SI Automation Flow\temp\pcb_20251019_093254\project.json"

with open(project_file) as f:
    info = json.load(f)

from pyedb import Edb, Siwave
edb_path = info['aedb_path']
edb = Edb(edb_path, version=info['edb_version'])

if info['cutout']['enabled']:
    edb.cutout(signal_nets=info['cutout']['signal_nets'],
               reference_nets=info['cutout']['reference_net'],
               extent_type = "Bounding",
               expansion_size=float(info['cutout']['expansion_size']),
               
               )
    
if info['solver'] == 'SIwave':
    setup = edb.create_siwave_syz_setup('mysetup')
    setup.add_frequency_sweep('mysweep', frequency_sweep=info['frequency_sweeps'])

elif info['solver'] == 'HFSS':
    setup = edb.create_hfss_setup('mysetup')
    sweep = setup.add_sweep('mysweep', frequency_set=info['frequency_sweeps'][0])
    for i in info['frequency_sweeps'][1:]:
        sweep.add(*i)


edb.save()
edb.close_edb()