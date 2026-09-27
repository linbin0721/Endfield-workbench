# API local development

Requires Python 3.11 or newer. In PowerShell, from `api/`:

For Linux Compose deployment and load testing, see [`../deploy/README.md`](../deploy/README.md). The local development command below is not the public deployment configuration.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Use one API worker. Task state and its bounded queue are held by that process; multiple Uvicorn workers would each create a separate queue. Set the variables in `.env.example` in the environment before launch. `CORS_ORIGINS` is a comma-separated list of exact browser origins. For example:

```powershell
$env:CORS_ORIGINS = "http://localhost:5173,https://your-frontend.example"
```

The question-number catalog needs PostgreSQL and the `CATALOG_DB_HOST`, `CATALOG_DB_PORT`, `CATALOG_DB_NAME`, `CATALOG_DB_USER`, and `CATALOG_DB_PASSWORD` variables. If they are absent or PostgreSQL is temporarily unavailable, screenshot recognition and solving continue while catalog queries return `503 CATALOG_UNAVAILABLE`.

Run tests and export the API contract from `api/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe export_openapi.py
```

Image regression tests use `samples/private/balloon-empty.jpg`, `balloon-solved.jpg`, `balloon-mobile-1.jpg`, and `balloon-mobile-3.jpg` when available. They generate the resized and board-only images from the original during the test. If a private image is absent, its corresponding sample test is explicitly skipped; bad-image, upload-limit, pixel-limit, and timeout tests still run. Set `BALLOON_TEST_SAMPLES_DIR` to an alternate sample directory to verify the suite without private images or to supply the named images from another location. A passing suite with skipped image tests does not verify recognition accuracy on real screenshots. Sparse-board diagnostics and the held-out mobile image boundary are recorded in [`../docs/mobile-recognition-implementation.md`](../docs/mobile-recognition-implementation.md).

`/api/v1/health` and `/api/v1/puzzles` are live. Balloon solving accepts JSON at `POST /api/v1/puzzles/balloon/solve` and returns a task ID; poll `GET /api/v1/tasks/{id}`. The request needs `rule_version: "center-torque-v1"`, `rows`, `columns`, `usable_cells` (zero-based row/column objects), and `inventory` (lift/count objects). The rule balances lift-weighted row and column distances from the geometric center. On a 5×5 board, the center has distance 0, adjacent cells 1, and the outer ring 2 on each axis. The solver returns `solved`, `unsatisfiable`, or `timeout` inside a succeeded task result. Its service-side time and search-node caps are `SOLVE_TIME_LIMIT_SECONDS` and `SOLVE_MAX_NODES`; clients cannot increase them. Both circuit operations still return `501 NOT_IMPLEMENTED`.

Balloon recognition accepts one multipart `image` at `POST /api/v1/puzzles/balloon/recognize`, returns a 202 task, and uses the same task polling route. The result is an editable draft: `cells` contains `usable` or `null` for each row-major cell, and each inventory row has nullable `lift` and `count`. Dark tile outlines establish the full board geometry; bright usable outlines mark cells as `usable`, while unconfirmed cells remain null. A missing inventory value stays null unless the high-confidence target total and all other known values determine exactly one valid count, lift, or complete row; every such derivation is reported in `issues`. `no_board`, `invalid_image`, `timeout`, and `failed` are distinct outcomes. Private image tests cover the supplied original screenshot, a generated resized version, a generated board-only crop, a completed board, and two sparse-board screenshots; this is not a general screen-photo accuracy claim.

Recognition also reads an optional `WL-A####` question number at confidence 0.95 or higher. A complete, solvable statement is recorded after API-process validation; the original image is not stored, only its SHA-256 digest for deduplication. Query `GET /api/v1/puzzles/balloon/catalog/{code}` to retrieve candidates. One distinct observation is `provisional`, a second digest matching the same statement is `verified`, and different statements remain side by side as `disputed` rather than overwriting each other.

Uploads are capped at 12 MiB per image, 12 MiB plus multipart overhead for the whole request, 20 million decoded pixels, two concurrent uploads by default, and 30 seconds to receive the request. The body cap is enforced before multipart parsing, regardless of Content-Length. A separate fixed-command process decodes and recognizes each image; its parent kills and waits on timeout before releasing the task slot. `RECOGNIZE_TIME_LIMIT_SECONDS` defaults to 25 (maximum 30), and `MAX_UPLOADS` defaults to 2. The original image is not persisted. The OCR package is `rapidocr-onnxruntime==1.4.4`, with its bundled models; its `opencv-python` dependency is constrained directly alongside NumPy and Pillow in `requirements.txt`. Linux runtime library needs will be covered by the deployment configuration in T05.

A running task cancellation records the request but keeps its worker slot until the work actually ends. Balloon search checks its own deadline and work cap, so a timed-out search ends and releases the slot. There is no general forced termination of arbitrary worker code; other long-running engines must not be enabled until isolated appropriately. Results are in memory and disappear after their TTL, retention limit, or API restart. Queue and results are local to one API process.
