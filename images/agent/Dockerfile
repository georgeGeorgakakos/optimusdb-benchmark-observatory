# Host control agent: started by deploy-host, shares the network namespace of odb-net (wg0),
# drives the sibling data-store containers through the Docker socket.
FROM docker:27-cli
RUN apk add --no-cache python3 iproute2-tc iptables iputils
COPY images/agent/agent.py /agent.py
ENTRYPOINT ["python3", "-u", "/agent.py"]
