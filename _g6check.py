import tempfile, pathlib
from tests.fixtures.generators import make_poststack3d
from sdip.equivalence.determinism import g6
if __name__ == "__main__":
    d = pathlib.Path(tempfile.mkdtemp())
    a = make_poststack3d(d / "s.sgy")
    r = g6(a.path, 1, workdir=d / "g6")
    print(r.status, "|", r.summary())
    import json; print(json.dumps(r.to_json(), indent=2)[:1500])
    print("LEFTOVER in workdir:", sorted(p.name for p in (d / "g6").iterdir()))
