"""P37 oracle: what OpenZGY's reader reads from each ZGY file (run outside SDIP, ``python -I``).

python -I prereg/P37_oracle.py PYZGY_SRC OUT.json FILE...
"""

import json
import sys

sys.path.insert(0, sys.argv[1])
from openzgy.api import ZgyReader  # noqa: E402

rows = {}
for p in sys.argv[3:]:
    with ZgyReader(p) as r:
        ih = r._meta._ih  # noqa: SLF001 - the projection string has no public reader property
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
json.dump(rows, open(sys.argv[2], "w"), indent=1)
