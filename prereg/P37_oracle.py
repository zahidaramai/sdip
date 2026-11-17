"""P37 oracle: what OpenZGY's reader reads from each ZGY file (run outside SDIP, ``python -I``).

python -I prereg/P37_oracle.py PYZGY_SRC OUT.json FILE...
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from openzgy.api import ZgyReader

rows = {}
for p in sys.argv[3:]:
    with ZgyReader(p) as r:
        ih = r._meta._ih
        rows[p.split("/")[-1]] = {
            "size": list(r.size),
            "annotstart": list(r.annotstart),
            "annotinc": list(r.annotinc),
            "zstart": r.zstart,
            "zinc": r.zinc,
            "corners": [list(c) for c in r.corners],
            "datatype": str(r.datatype).split(".")[-1],
            "projection": ih._hprjsys or "",
        }
with Path(sys.argv[2]).open("w") as out:
    json.dump(rows, out, indent=1)
