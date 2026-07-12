FROM python@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    torch==2.7.1 \
    numpy==2.2.6 \
    pyyaml==6.0.2 \
    zarr==2.18.7
USER 65532:65532
WORKDIR /workspace
