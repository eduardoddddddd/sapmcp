FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib \
    LD_LIBRARY_PATH=/opt/sap/nwrfcsdk/lib

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 libuuid1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 sapmcp

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

USER sapmcp
WORKDIR /home/sapmcp

CMD ["sapmcp"]
