import re, os
import sys
import json
from pathlib import Path

#json_path = '../data2/simulation.json'
json_path = sys.argv[1]

with open(json_path) as f:
    info = json.load(f)
    
edb_path = info['aedb_path'].replace('.aedb', '_applied.aedb')
from pyaedt import Hfss3dLayout

hfss = Hfss3dLayout(edb_path, version=info['solver_version'], non_graphical=True)

hfss.export_touchstone_on_completion()
hfss.analyze()

root = Path(info['aedb_path'].replace('.aedb', '_applied.aedtexport'))
pattern = re.compile(r"\.s(\d{1,3})p$", re.IGNORECASE)

# 遞迴搜尋所有 sNp 檔案
matched_files = [
    p.resolve() for p in root.rglob("*")
    if p.is_file() and pattern.search(p.name)
]

# 釋放 AEDT
hfss.release_desktop()

if matched_files:
    # 依照最後修改時間排序，取最新的
    latest_file = max(matched_files, key=lambda p: p.stat().st_mtime)
    touchstone_path = str(latest_file)
    print("Latest Touchstone file:", touchstone_path)

    # 儲存結果 JSON
    output_dir = Path(json_path).parent
    result_json_path = output_dir / "result.json"
    with open(result_json_path, "w") as f:
        json.dump({"touchstone_path": touchstone_path}, f, indent=2)
else:
    print("Error: No Touchstone file found.")
    sys.exit(1)


