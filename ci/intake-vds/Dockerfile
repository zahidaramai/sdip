# OpenVDS reader for `sdip intake` (D-514: OpenVDS runs in a Linux container; its wheels are
# Linux/Windows x86-64 only). Build: docker build --platform linux/amd64 -t sdip-intake-vds:3.4.9 ci/intake-vds
# Run with --network none and the upload mounted read-only.
FROM python:3.12-slim
RUN pip install --no-cache-dir openvds==3.4.9 numpy==2.2.6
COPY vds_probe.py /opt/sdip/vds_probe.py
ENTRYPOINT ["python", "-I", "/opt/sdip/vds_probe.py"]
