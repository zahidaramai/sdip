"""P38 generator: an F3 sub-volume as SEG-Y, then VDS files written by OpenVDS's SEGYImport.

    python -I prereg/P38_make_vds.py F3_SEGY OUT_DIR IMAGE

F3 is revision 0, IEEE float32, 462 samples, inline-major with 951 crosslines per inline
(measured by P36). Inlines 100-299 x crosslines 300-599 (field-ok: public F3 survey index
ranges). The import runs in the container with networking off.
"""

import subprocess
import sys
from pathlib import Path

NS, NXL = 462, 951
IL0, IL_N, XL0, XL_N = 100, 200, 300, 300
WKT = (
    'PROJCS["ED50 / UTM zone 31N",GEOGCS["ED50",DATUM["European_Datum_1950",SPHEROID['
    '"International 1924",6378388,297]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532'
    '925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],'
    'PARAMETER["central_meridian",3],PARAMETER["scale_factor",0.9996],PARAMETER["fals'
    'e_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG'
    '","23031"]]'
)


def main(segy: str, out_dir: str, image: str) -> None:
    """Write the SEG-Y subset, import it twice, cut a copy."""
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    trace = 240 + 4 * NS
    sub = out / "f3_sub.sgy"
    with Path(segy).open("rb") as src, sub.open("wb") as dst:
        dst.write(src.read(3600))
        for k in range(IL_N):
            src.seek(3600 + ((IL0 - 100 + k) * NXL + (XL0 - 300)) * trace)
            dst.write(src.read(XL_N * trace))
    base = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--network",
        "none",
        "-v",
        f"{out}:/w",
        "--entrypoint",
        "SEGYImport",
        image,
    ]
    subprocess.run([*base, "--vdsfile", "/w/f3_sub.vds", "/w/f3_sub.sgy"], check=True)  # noqa: S603
    subprocess.run(  # noqa: S603 - fixed argv built here
        [*base, "--crs-wkt", WKT, "--vdsfile", "/w/f3_sub_crs.vds", "/w/f3_sub.sgy"], check=True
    )
    data = (out / "f3_sub.vds").read_bytes()
    (out / "f3_sub_cut.vds").write_bytes(data[:-1000])
    sub.unlink()


if __name__ == "__main__":
    main(*sys.argv[1:4])
