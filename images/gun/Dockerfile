FROM node:22-bookworm-slim
WORKDIR /app
COPY images/gun/package.json ./
RUN npm install --omit=dev
COPY harness/wrappers/gun_http.mjs ./gun_http.mjs
COPY images/gun/entry.sh /entry.sh
RUN sed -i 's/\r$//' /entry.sh && chmod +x /entry.sh && mkdir -p /data
ENTRYPOINT ["/entry.sh"]
