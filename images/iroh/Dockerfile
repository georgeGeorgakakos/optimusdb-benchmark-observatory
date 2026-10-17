FROM rust:1.91-bookworm AS build
WORKDIR /src
COPY harness/wrappers/iroh_http/Cargo.toml harness/wrappers/iroh_http/Cargo.lock ./
COPY harness/wrappers/iroh_http/src ./src
RUN cargo build --release --locked && cp target/release/iroh_http /iroh_http

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=build /iroh_http /usr/local/bin/iroh_http
COPY images/iroh/entry.sh /entry.sh
RUN sed -i 's/\r$//' /entry.sh && chmod +x /entry.sh && mkdir -p /data
ENTRYPOINT ["/entry.sh"]
