#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

YES=false
PRESERVE_IMAGES=false
for arg in "$@"; do
  case "${arg}" in
    --yes)
      YES=true
      ;;
    --preserve-images)
      PRESERVE_IMAGES=true
      ;;
    *)
      echo "Unknown argument: ${arg}"
      echo "Usage: $0 [--yes] [--preserve-images]"
      echo "  --yes              run without interactive confirmation"
      echo "  --preserve-images  do not remove compose-built images"
      exit 1
      ;;
  esac
done

echo "[cleanup] project root: ${ROOT_DIR}"
echo "[cleanup] target: de_matrix compose stack + related containers/networks/volumes"
echo "[cleanup] this will stop and remove containers, networks and volumes for de_matrix"
if [[ "${PRESERVE_IMAGES}" == "false" ]]; then
  echo "[cleanup] compose-built images will also be removed (--rmi local)"
fi

if [[ "${YES}" != "true" ]]; then
  read -r -p "Continue cleanup? [y/N] " ans
  if [[ "${ans}" != "y" && "${ans}" != "Y" ]]; then
    echo "[cleanup] cancelled"
    exit 0
  fi
fi

DOWN_ARGS=(down --remove-orphans --volumes)
if [[ "${PRESERVE_IMAGES}" == "false" ]]; then
  DOWN_ARGS+=(--rmi local)
fi

echo "[cleanup] compose down (${DOWN_ARGS[*]})"
"${COMPOSE[@]}" "${DOWN_ARGS[@]}"

echo "[cleanup] remove leftovers by container name prefix"
mapfile -t leftovers < <(docker ps -aq --filter "name=de-matrix-")
if [[ "${#leftovers[@]}" -gt 0 ]]; then
  docker rm -f "${leftovers[@]}" >/dev/null || true
fi

echo "[cleanup] remove compose networks by prefix (de_matrix_)"
mapfile -t net_names < <(docker network ls --format '{{.Name}}' | awk '/^de_matrix_/ {print}')
if [[ "${#net_names[@]}" -gt 0 ]]; then
  docker network rm "${net_names[@]}" >/dev/null || true
fi

echo "[cleanup] remove compose volumes by prefix (de_matrix_)"
mapfile -t vol_names < <(docker volume ls --format '{{.Name}}' | awk '/^de_matrix_/ {print}')
if [[ "${#vol_names[@]}" -gt 0 ]]; then
  docker volume rm "${vol_names[@]}" >/dev/null || true
fi

echo "[cleanup] done"
