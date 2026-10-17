# OptimusDB agent for the benchmark. The base image is built by deploy-host from your repository's own
# Dockerfile (git URL + pinned commit, or a local checkout): docker build -t odb-optimusdb-base <source>
ARG OPTIMUSDB_BASE=odb-optimusdb-base:latest
FROM ${OPTIMUSDB_BASE}
COPY images/optimusdb/entry.sh /entry.sh
RUN sed -i 's/\r$//' /entry.sh && chmod +x /entry.sh
ENTRYPOINT ["/entry.sh"]
