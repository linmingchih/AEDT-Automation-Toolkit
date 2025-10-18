import re, os
import sys
import json
from pathlib import Path

#project_file = '../data2/project.json'
project_file = sys.argv[1]

with open(project_file) as f:
    info = json.load(f)
    
edb_path = info['aedb_path']
from pyaedt import Hfss3dLayout

hfss = Hfss3dLayout(edb_path, version=info['solver_version'], non_graphical=True)

hfss.export_touchstone_on_completion()
hfss.analyze()
touchstone_path = os.path.join(os.path.dirname(info['aedb_path']), f'model.s{len(info["ports"])}p')
hfss.export_touchstone('mysetup', 'mysweep', output_file=touchstone_path)

info["touchstone_path"] = touchstone_path
with open(project_file, "w") as f:
    json.dump(info, f, indent=2)

