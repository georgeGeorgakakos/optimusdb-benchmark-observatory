# Load generator / experiment driver. Runs on the bench host, in the network namespace of its odb-net (overlay 10.88.0.2).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends procps iputils-ping && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir httpx pyyaml numpy scipy pandas pytest openpyxl
WORKDIR /bench
COPY harness/ /bench/
# dashboard analysis + report renderer: run-all saves the evaluation report with each run (dashboard/report_cli.py)
COPY dashboard/ /dashboard/
ENV BENCH_RESULTS=/results PYTHONUNBUFFERED=1
ENTRYPOINT ["sleep", "infinity"]
