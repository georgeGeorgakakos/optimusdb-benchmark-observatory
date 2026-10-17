FROM rust:1.89-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends clang mold git && rm -rf /var/lib/apt/lists/*
ARG CORROSION_REF
RUN git clone https://github.com/superfly/corrosion /src && cd /src && git checkout ${CORROSION_REF}
WORKDIR /src
RUN cargo build --release -p corrosion && cp target/release/corrosion /corrosion

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates sqlite3 && rm -rf /var/lib/apt/lists/*
COPY --from=build /corrosion /usr/local/bin/corrosion
COPY images/corrosion/schemas /etc/corrosion/schemas
COPY images/corrosion/entry.sh /entry.sh
RUN sed -i 's/\r$//' /entry.sh && chmod +x /entry.sh && mkdir -p /data
ENTRYPOINT ["/entry.sh"]
