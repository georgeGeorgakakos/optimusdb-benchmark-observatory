# dhtnode with the REST proxy, built from the pinned release on the project's own dependency image.
FROM ghcr.io/savoirfairelinux/opendht/opendht-deps:latest AS build
ARG OPENDHT_REF
RUN git clone --depth 1 --branch ${OPENDHT_REF} https://github.com/savoirfairelinux/opendht /opendht \
 && cd /opendht && mkdir build && cd build \
 && cmake .. -DCMAKE_INSTALL_PREFIX=/usr -DBUILD_TESTING=Off -DOPENDHT_TOOLS=On -DOPENDHT_PROXY_SERVER=On \
          -DOPENDHT_PROXY_CLIENT=On -DOPENDHT_PYTHON=Off -DOPENDHT_C=Off \
 && make -j"$(nproc)" && make install DESTDIR=/out
FROM ghcr.io/savoirfairelinux/opendht/opendht-deps:latest
COPY --from=build /out/usr /usr
COPY images/opendht/entry.sh /entry.sh
RUN sed -i 's/\r$//' /entry.sh && chmod +x /entry.sh
ENTRYPOINT ["/entry.sh"]
