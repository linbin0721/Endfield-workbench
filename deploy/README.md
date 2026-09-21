# Linux API deployment and capacity check

This directory deploys the API behind Caddy. The Vercel site remains a separate static build; its public `VITE_API_BASE_URL` must be `https://` plus the API domain. The API container has no published host port. Caddy is the only public entry point on ports 80 and 443.

## Configure and launch

On the Linux host with Docker Engine and Compose installed, point a real DNS record at the host and allow inbound TCP 80/443. Copy `.env.example` to `.env` and fill both required values:

```sh
cd deploy
cp .env.example .env
# Edit .env: API_DOMAIN is the API hostname without a scheme;
# CORS_ORIGINS is the exact HTTPS origin of the Vercel frontend.
docker compose config
docker compose up --build -d
docker compose ps
curl -fsS "https://<your-real-api-domain>/api/v1/health"
```

Compose refuses empty `API_DOMAIN` and `CORS_ORIGINS`. If the frontend uses more than one exact origin, use a comma-separated `CORS_ORIGINS` list. The domain must resolve publicly and ports 80/443 must be reachable for Caddy to obtain and renew a certificate. Caddy keeps certificate data in `caddy_data`; do not discard this volume during routine updates. Set Vercel's `VITE_API_BASE_URL=https://<API_DOMAIN>` and build/deploy the frontend separately. Review `docker compose logs --tail=100 api caddy` and `docker compose ps` after starting.

The API runs one Uvicorn process with two compute processes, eight queued tasks, and two upload slots. Compose initially caps it at 2 CPUs, 2 GiB RAM and 128 processes; Caddy has separate 0.5 CPU / 256 MiB / 64 process limits. These are initial safeguards, not measured capacity. The API uses a read-only filesystem, a writable 128 MiB temporary filesystem, and a non-root account. `opencv-python` uses Linux `libgl1`, `libglib2.0-0`, and `libgomp1` installed in the image. The build context is `api/`; only requirements and application code are copied into the image. Private screenshots are outside the build context. Container logs rotate at 10 MiB × 3 files each.

Caddy streams requests upstream without `request_buffers`. Its 13 MB whole-request ceiling also limits JSON solve submissions; the API separately enforces a 12 MiB image limit and a 12 MiB plus 64 KiB multipart body limit. Uploaded originals are not persisted. Compose gives API shutdown up to 180 seconds. During shutdown, the task manager cancels queued jobs and waits for already running work, including an OCR child within its timeout boundary. The grace period is not a guarantee against abnormal process stalls.

## Load test

Install the API development dependencies on the load-driver machine (`pip install -r api/requirements-dev.txt`). The driver is `api/bench/load_test.py`; it does not run inside the API container. Run solve and recognition separately, with a real unaltered screenshot for recognition:

```sh
cd .. # return to the project root after the deployment commands above
python api/bench/load_test.py --mode solve --api-url "https://<your-real-api-domain>" --requests 100 --concurrency 100 --output solve-load.json
python api/bench/load_test.py --mode recognize --api-url "https://<your-real-api-domain>" --image /private/path/balloon-empty.jpg --requests 100 --concurrency 100 --output recognition-load.json
```

The script reports HTTP 202, HTTP 429, other statuses, transport errors, terminal task status and result outcome separately. It records submission and end-to-end p50/p95 latency and samples `/api/v1/health` during the run. HTTP 202 only means queued or started; HTTP 429 is an intentional refusal under limits. Recognition mode fails before sending requests if the real image is missing. For a local API process, pass `--pid <API_PID>` to sample the API process tree. The script sums resident memory (RSS) across processes, which can count shared pages more than once, and estimates CPU as a percentage of one logical core from positive deltas for processes seen in consecutive samples. Short memory peaks, CPU used before a new child first appears in a sample, and CPU used by children that exit between samples can be missed. The load driver itself is outside that process tree.

Keep the reports with the host CPU count, RAM, API limits, image size, and network path used. A loopback run cannot establish performance on a future server or real user network. Docker Engine is unavailable on the current Windows development host, so the image and Linux runtime still require deployment-host verification.
