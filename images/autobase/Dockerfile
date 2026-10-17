FROM node:22-bookworm-slim
WORKDIR /app
COPY images/autobase/package.json ./
RUN npm install --omit=dev
COPY harness/wrappers/autobase_http.mjs ./autobase_http.mjs
COPY images/autobase/entry.sh /entry.sh
RUN sed -i 's/\r$//' /entry.sh && chmod +x /entry.sh && mkdir -p /data
ENTRYPOINT ["/entry.sh"]
