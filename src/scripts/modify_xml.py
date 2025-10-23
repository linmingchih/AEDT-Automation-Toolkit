import sys
import json
from pyedb import Edb

json_path = sys.argv[1]

with open(json_path) as f:
    info = json.load(f)

edb = Edb(info['aedb_path'], version=info['edb_version'])

edb.stackup.load(info['xml_path'])
edb.save()
edb.close_edb()
