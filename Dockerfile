FROM docker.m.daocloud.io/library/node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm config set replace-registry-host always \
    && npm ci
COPY . .
RUN npm run build

FROM docker.m.daocloud.io/library/node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
