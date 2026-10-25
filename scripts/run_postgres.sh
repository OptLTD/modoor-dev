#!/usr/bin/env bash
# 启动 pgvector Postgres。数据在命名卷里，停止或删除容器都不会清库。
# 只有空数据目录的第一次启动会按 POSTGRES_DB 建库。
#
#   POSTGRES_PASSWORD='你的密码' ./scripts/run_postgres.sh
#
# 可选：POSTGRES_DB POSTGRES_USER POSTGRES_PORT POSTGRES_IMAGE
#       POSTGRES_CONTAINER POSTGRES_VOLUME
set -euo pipefail

IMAGE="${POSTGRES_IMAGE:-pgvector/pgvector:pg18}"
NAME="${POSTGRES_CONTAINER:-modoor-pg}"
VOLUME="${POSTGRES_VOLUME:-modoor-pg}"
DB="${POSTGRES_DB:-modoor}"
PORT="${POSTGRES_PORT:-5432}"
USERNAME="${POSTGRES_USER:-modoor}"
PASSWORD="${POSTGRES_PASSWORD:-}"

if [[ -z "${PASSWORD}" ]]; then
  echo "请设置 POSTGRES_PASSWORD" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 docker" >&2
  exit 1
fi

# Postgres 18 的数据在 /var/lib/postgresql/<大版本>/ 下。
# 卷要挂在 /var/lib/postgresql，不能再挂到 /var/lib/postgresql/data。
DATA_MOUNT="/var/lib/postgresql"

create_container() {
  docker volume create "${VOLUME}" >/dev/null
  docker run -d \
    --name "${NAME}" \
    --restart unless-stopped \
    -e "POSTGRES_USER=${USERNAME}" \
    -e "POSTGRES_PASSWORD=${PASSWORD}" \
    -e "POSTGRES_DB=${DB}" \
    -p "${PORT}:5432" \
    -v "${VOLUME}:${DATA_MOUNT}" \
    "${IMAGE}" >/dev/null
  echo "已创建: ${NAME}，库 ${DB}，卷 ${VOLUME}"
}

if docker container inspect "${NAME}" >/dev/null 2>&1; then
  mount_at="$(docker inspect -f '{{range .Mounts}}{{.Destination}}{{"\n"}}{{end}}' "${NAME}")"
  if ! printf '%s\n' "${mount_at}" | grep -qx "${DATA_MOUNT}"; then
    docker rm -f "${NAME}" >/dev/null
    docker volume rm "${VOLUME}" >/dev/null
    echo "旧挂载无法被 Postgres 18 使用，已删掉容器和卷 ${VOLUME}。"
    create_container
  else
    state="$(docker inspect -f '{{.State.Status}}' "${NAME}")"
    if [[ "${state}" == "running" ]]; then
      echo "已在运行: ${NAME}"
    else
      docker start "${NAME}" >/dev/null
      echo "已启动: ${NAME}（沿用卷 ${VOLUME}）"
    fi
  fi
else
  create_container
fi

for _ in $(seq 1 30); do
  if docker exec "${NAME}" pg_isready -U "${USERNAME}" -d "${DB}" >/dev/null 2>&1; then
    echo "postgresql://${USERNAME}@127.0.0.1:${PORT}/${DB}"
    exit 0
  fi
  sleep 1
done

echo "容器已起来，但 30 秒内还没就绪。看日志: docker logs ${NAME}" >&2
exit 1
