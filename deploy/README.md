# Linux API deployment and capacity check

This directory deploys the API, its internal PostgreSQL catalog, and Caddy. A separately hosted static frontend uses `VITE_API_BASE_URL` to call the API directly. In standalone mode neither the API nor PostgreSQL publishes a host port; Caddy is the only public entry point on ports 80 and 443.

On a host where an existing Nginx already owns public TCP 80/443, use `compose.vps.yaml` as an overlay instead: the API is then published on loopback only and Caddy stays disabled. See [API-only host behind an existing Nginx](#api-only-host-behind-an-existing-nginx).

## Configure and launch

On the Linux host with Docker Engine and Compose installed, point a real DNS record at the host and allow inbound TCP 80/443. Copy `.env.example` to `.env` and fill every required value:

```sh
cd deploy
cp .env.example .env
# Edit .env: API_DOMAIN is the API hostname without a scheme;
# CORS_ORIGINS is the exact HTTPS origin of the static frontend;
# CATALOG_DB_PASSWORD is a new random password kept only in this ignored file.
docker compose config
docker compose up --build -d
docker compose ps
curl -fsS "https://<your-real-api-domain>/api/v1/health"
```

Compose refuses empty domain, CORS, or catalog database values. If the frontend uses more than one exact origin, use a comma-separated `CORS_ORIGINS` list. The domain must resolve publicly and ports 80/443 must be reachable for Caddy to obtain and renew a certificate. Caddy keeps certificate data in `caddy_data`; the catalog uses the `catalog_data` volume. Do not discard either volume during routine updates. Set the frontend's `VITE_API_BASE_URL=https://<API_DOMAIN>` and build/deploy it separately. Review `docker compose logs --tail=100 api db caddy` and `docker compose ps` after starting.

The API runs one Uvicorn process with two compute processes, eight queued tasks, and two upload slots. Compose initially caps it at 2 CPUs, 2 GiB RAM and 128 processes; PostgreSQL has 1 CPU, 512 MiB RAM and 128 processes; Caddy has separate 0.5 CPU / 256 MiB / 64 process limits. These are initial safeguards, not measured capacity. The API uses a read-only filesystem, a writable 128 MiB temporary filesystem, and a non-root account. `opencv-python` uses Linux `libgl1`, `libglib2.0-0`, and `libgomp1` installed in the image. The build context is `api/`; only requirements and application code are copied into the image. Private screenshots are outside the build context. Container logs rotate at 10 MiB × 3 files each.

Caddy streams requests upstream without `request_buffers`. Its 13 MB whole-request ceiling also limits JSON solve submissions; the API separately enforces a 12 MiB image limit and a 12 MiB plus 64 KiB multipart body limit. Uploaded originals are not persisted. The catalog stores normalized puzzle statements and image SHA-256 values only. Compose gives API shutdown up to 180 seconds. During shutdown, the task manager cancels queued jobs and waits for already running work, including an OCR child within its timeout boundary. The grace period is not a guarantee against abnormal process stalls.

## API-only host behind an existing Nginx

`compose.vps.yaml` is an overlay for a host where an existing Nginx already owns public TCP 80/443 and terminates TLS. It is always combined with the base file and changes only three things:

- the API is published on loopback: `127.0.0.1:18000` on the host to container port `8000`;
- `caddy` is placed in the `caddy` profile, so it is not created and cannot claim 80/443 unless that profile is explicitly enabled;
- the top-level Compose project name is pinned to `endfield-workbench`.

A shared VPS usually runs several Compose projects, so the project name must not stay implicit: without it Compose would derive the name `deploy` from this directory, which is generic enough to collide with another stack and would make `docker compose ps`, `down`, logs and container names ambiguous across projects. The overlay pins `name: endfield-workbench`, so containers are named `endfield-workbench-api-1` (and `endfield-workbench-caddy-1` if the `caddy` profile is ever enabled). Use those names with `docker logs` and `docker inspect`; every `docker compose -f compose.yaml -f compose.vps.yaml ...` command run with this file already targets the `endfield-workbench` project. An explicit `-p <other>` or `COMPOSE_PROJECT_NAME` still takes precedence over the file, so do not set them for this deployment.

Standalone mode starts `api`, `db`, and `caddy`, keeps the directory-derived `deploy` project name, and publishes neither the API nor PostgreSQL directly. `docker compose -f compose.yaml -f compose.vps.yaml config --services` prints `db` and `api` because Caddy remains profile-gated on the shared VPS.

Compose interpolates the base file before merging, so `API_DOMAIN`, `CORS_ORIGINS`, and all `CATALOG_DB_*` values must be set even though `API_DOMAIN` is unused while Caddy stays disabled. Keep any placeholder `API_DOMAIN` in `deploy/.env` and set `CORS_ORIGINS` to the exact HTTPS origin of the deployed frontend; the API rejects origins outside the list.

```sh
cd deploy
cp .env.example .env
# Edit .env: CORS_ORIGINS=https://<your-frontend-host>
# API_DOMAIN is only read by the base file's validation in this mode.
docker compose -f compose.yaml -f compose.vps.yaml config --quiet
docker compose -f compose.yaml -f compose.vps.yaml config --services   # prints "db" and "api"
docker compose -f compose.yaml -f compose.vps.yaml up --build -d
docker compose -f compose.yaml -f compose.vps.yaml ps
curl -fsS http://127.0.0.1:18000/api/v1/health
```

The same validation runs without real values or secrets:

```sh
API_DOMAIN=api.example.invalid CORS_ORIGINS=https://web.example.invalid \
  CATALOG_DB_NAME=endfield_catalog CATALOG_DB_USER=endfield_catalog CATALOG_DB_PASSWORD=example-only \
  docker compose -f compose.yaml -f compose.vps.yaml config --quiet
```

### Catalog backup

Back up the catalog before an update that changes its schema. The command reads database names from the container and writes the dump on the host:

```sh
cd deploy
mkdir -p backups
docker compose -f compose.yaml -f compose.vps.yaml exec -T db \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "backups/catalog-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

Treat dumps as private. Test restoration separately before relying on a backup; restoring with `pg_restore --clean` replaces current catalog data.

### Keep exactly one Uvicorn worker

`api/Dockerfile` already runs `python -m uvicorn ... --workers 1`, and the overlay must not change that. Do not add a `command:` to `api`, do not raise `--workers` above 1, and do not scale the service with `--scale api=N` or `deploy.replicas`. The task queue, running jobs and results live inside the single process; extra Uvicorn workers would answer from separate queues and make valid task IDs return 404 depending on which process handles the request.

### VPS status, update, and rollback

Run status and logs from the deployed checkout:

```sh
cd /root/project/EndfieldWorkbench/deploy
docker compose -f compose.yaml -f compose.vps.yaml ps
docker compose -f compose.yaml -f compose.vps.yaml logs --tail=100 api db
curl -fsS http://127.0.0.1:18000/api/v1/health
curl -fsS https://api.linbin.org/endfield/api/v1/health
```

Before an update, create and validate the catalog backup shown above. Then fast-forward the checkout, validate and rebuild the API, and publish a versioned static release:

```sh
cd /root/project/EndfieldWorkbench
git fetch origin main
git pull --ff-only origin main

cd deploy
docker compose -f compose.yaml -f compose.vps.yaml config --quiet
docker compose -f compose.yaml -f compose.vps.yaml build api
docker compose -f compose.yaml -f compose.vps.yaml up -d --no-deps api

cd ../web
npm ci --include=dev
VITE_API_BASE_URL=https://api.linbin.org/endfield npm run build
release="$(git -C .. rev-parse --short=7 HEAD)"
test ! -e "/var/www/endfield-workbench/releases/$release"
install -d -m 0755 "/var/www/endfield-workbench/releases/$release"
cp -a dist/. "/var/www/endfield-workbench/releases/$release/"
ln -s "/var/www/endfield-workbench/releases/$release" /var/www/endfield-workbench/current.next
mv -Tf /var/www/endfield-workbench/current.next /var/www/endfield-workbench/current
```

EW-018 (`f2d3409`) reduces OCR detection scaling. Roll back only the API to the retained EW-012 image:

```sh
cd /root/project/EndfieldWorkbench/deploy
docker tag endfield-workbench-api:rollback-f170d1e-ew018-20261003T184434Z endfield-workbench-api:latest
docker compose -f compose.yaml -f compose.vps.yaml up -d --no-deps --force-recreate api
curl -fsS http://127.0.0.1:18000/api/v1/health
```

The schema and static release are compatible with both images; no database restoration or frontend switch is needed. The pre-update dump is `backups/catalog-before-ew018-20261003T184434Z.dump` (`pg_restore --list` validated; an actual restoration was not tested).

EW-012 (`f170d1e`) changed only the API OCR path. Roll it back to the previous API image without changing the static frontend or database:

```sh
docker tag endfield-workbench-api:rollback-4056d5e-20260929T1830Z endfield-workbench-api:latest
cd /root/project/EndfieldWorkbench/deploy
docker compose -f compose.yaml -f compose.vps.yaml up -d --no-deps --force-recreate api
```

EW-011 (`f1f66ba`) changed only the static frontend. Roll back its corrected fallback colors without restarting the API:

```sh
ln -s /var/www/endfield-workbench/releases/a6fe91b /var/www/endfield-workbench/current.rollback
mv -Tf /var/www/endfield-workbench/current.rollback /var/www/endfield-workbench/current
```

To also roll back EW-010 (`a6fe91b`) and its numbered regions and unified guide pieces without restarting the API:

```sh
ln -s /var/www/endfield-workbench/releases/abc4e8b /var/www/endfield-workbench/current.rollback
mv -Tf /var/www/endfield-workbench/current.rollback /var/www/endfield-workbench/current
```

To also roll back EW-009 (`abc4e8b`) and its simplified circuit guide without restarting the API:

```sh
ln -s /var/www/endfield-workbench/releases/d8dc3bf /var/www/endfield-workbench/current.rollback
mv -Tf /var/www/endfield-workbench/current.rollback /var/www/endfield-workbench/current
```

To also roll back EW-008 (`d8dc3bf`) and its unified-piece rendering without restarting the API:

```sh
ln -s /var/www/endfield-workbench/releases/4056d5e /var/www/endfield-workbench/current.rollback
mv -Tf /var/www/endfield-workbench/current.rollback /var/www/endfield-workbench/current
```

To roll the earlier EW-007 release (`4056d5e`) back to EW-006, switch both the static site and API image without changing the backward-compatible database column:

```sh
ln -s /var/www/endfield-workbench/releases/90b762f /var/www/endfield-workbench/current.rollback
mv -Tf /var/www/endfield-workbench/current.rollback /var/www/endfield-workbench/current

docker tag endfield-workbench-api:rollback-90b762f-20260929T085002Z endfield-workbench-api:latest
cd /root/project/EndfieldWorkbench/deploy
docker compose -f compose.yaml -f compose.vps.yaml up -d --no-deps --force-recreate api
```

Stop only this project's API without removing the database volume:

```sh
cd /root/project/EndfieldWorkbench/deploy
docker compose -f compose.yaml -f compose.vps.yaml stop api
```

The release did not modify Nginx. Its pre-release archive is `deploy/.local-backups/nginx-ew006-e-20260929T052718Z.tar.gz`. If a later manual change to these two site files must be undone, restore and validate them with:

```sh
cd /
tar -xzf /root/project/EndfieldWorkbench/deploy/.local-backups/nginx-ew006-e-20260929T052718Z.tar.gz -C /
nginx -t
systemctl reload nginx
```

### Nginx example and the `/endfield` prefix

The API has no path-prefix configuration and does not need one: Nginx strips the prefix before forwarding. The trailing slash on `proxy_pass` is what removes `/endfield`, so the API still receives `/api/v1/...`:

```nginx
location = /endfield { return 301 /endfield/; }
location /endfield/ {
    proxy_pass http://127.0.0.1:18000/;  # trailing slash strips /endfield
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 13m;
    proxy_request_buffering off;
}
```

To serve the API at the host root instead, drop the prefix and use `location / { proxy_pass http://127.0.0.1:18000; }`; only the Vercel `VITE_API_BASE_URL` value changes.

`client_max_body_size 13m` mirrors Caddy's 13 MB whole-request ceiling from standalone mode: it still admits the 12 MiB image plus multipart overhead and rejects larger bodies before they reach the API. `proxy_request_buffering off` keeps uploads streaming to the API instead of buffering the whole body on the proxy, as required by the deployment design. Nginx terminates TLS on this host, so Caddy stays disabled and the `caddy` profile must not be enabled here: it would try to bind 80/443 as well.

On Vercel, set `VITE_API_BASE_URL=https://<your-host>/endfield` (no trailing slash). The frontend appends `/api/v1/...` to that value, so including the prefix is supported. The Vercel origin must also appear in `CORS_ORIGINS`, because the static site calls the API cross-origin.

## Load test

Install the API development dependencies on the load-driver machine (`pip install -r api/requirements-dev.txt`). The driver is `api/bench/load_test.py`; it does not run inside the API container. Run solve and recognition separately, with a real unaltered screenshot for recognition:

```sh
cd .. # return to the project root after the deployment commands above
python api/bench/load_test.py --mode solve --api-url "https://<your-real-api-domain>" --requests 100 --concurrency 100 --output solve-load.json
python api/bench/load_test.py --mode recognize --api-url "https://<your-real-api-domain>" --image /private/path/balloon-empty.jpg --requests 100 --concurrency 100 --output recognition-load.json
```

When the API is reached through the Nginx overlay, pass `--api-url "https://<your-host>/endfield"` instead; the driver appends `/api/v1/...` to that base URL.

The script reports HTTP 202, HTTP 429, other statuses, transport errors, terminal task status and result outcome separately. It records submission and end-to-end p50/p95 latency and samples `/api/v1/health` during the run. HTTP 202 only means queued or started; HTTP 429 is an intentional refusal under limits. Recognition mode fails before sending requests if the real image is missing. For a local API process, pass `--pid <API_PID>` to sample the API process tree. The script sums resident memory (RSS) across processes, which can count shared pages more than once, and estimates CPU as a percentage of one logical core from positive deltas for processes seen in consecutive samples. Short memory peaks, CPU used before a new child first appears in a sample, and CPU used by children that exit between samples can be missed. The load driver itself is outside that process tree.

Keep the reports with the host CPU count, RAM, API limits, image size, and network path used. A loopback run cannot establish performance on a future server or real user network. The Linux image and runtime were first verified on a VPS on 2026-09-25; repeat these checks on future hosts.
