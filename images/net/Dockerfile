# Network container of one host: owns the network namespace shared by the agent and the data stores.
# wg0 = WireGuard overlay between all hosts (10.88.0.0/24); tc/netem and iptables act on wg0.
FROM alpine:3.20
RUN apk add --no-cache bash wireguard-tools iproute2 iproute2-tc iptables iputils python3 curl \
 && (apk add --no-cache wireguard-go 2>/dev/null || echo 'wireguard-go not packaged: kernel WireGuard only (not needed in single-machine mode)')
COPY images/net/net-entrypoint.sh /usr/local/bin/net-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/net-entrypoint.sh && chmod +x /usr/local/bin/net-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/net-entrypoint.sh"]
