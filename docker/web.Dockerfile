FROM node:24-alpine

WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./

EXPOSE 5173
# The Vite dev server, as in `make web`; --host makes it reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host"]
