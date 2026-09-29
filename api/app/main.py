from contextlib import asynccontextmanager
import hashlib

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.datastructures import UploadFile

from app.catalog.models import CatalogEntry
from app.catalog.circuit_models import CircuitCatalogEntry
from app.catalog.circuit_rules import normalize_circuit_code
from app.catalog.circuit_service import CircuitCatalogService
from app.catalog.circuit_store import circuit_catalog_store_from_settings
from app.catalog.rules import normalize_code
from app.catalog.service import CatalogService
from app.catalog.store import CatalogUnavailable, catalog_store_from_settings
from app.config import Settings, load_settings
from app.models import ErrorResponse, PuzzleCapability, TaskView
from app.puzzles import PUZZLES
from app.puzzles.balloon.model import BalloonPuzzle, BalloonSolveResult
from app.puzzles.balloon.recognize import BalloonRecognitionResult, recognize_balloon_job
from app.puzzles.balloon.solve import solve_balloon_job
from app.puzzles.circuit.model import CircuitPuzzle, CircuitSolveResult
from app.puzzles.circuit.recognize import (
    CircuitRecognitionResult,
    recognize_circuit_job,
)
from app.puzzles.circuit.solve import solve_circuit_job
from app.tasks import QueueFull, TaskManager
from app.upload_limit import LimitedRecognitionUpload, MAX_IMAGE_BYTES


class HealthResponse(BaseModel):
    status: str


class BalloonSolveTaskView(TaskView):
    result: BalloonSolveResult | None = None


class BalloonRecognitionTaskView(TaskView):
    result: BalloonRecognitionResult | None = None


class CircuitRecognitionTaskView(TaskView):
    result: CircuitRecognitionResult | None = None


class CircuitSolveTaskView(TaskView):
    result: CircuitSolveResult | None = None


def error_response(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers=headers)


def create_app(
    settings: Settings | None = None,
    catalog: CatalogService | None = None,
    circuit_catalog: CircuitCatalogService | None = None,
) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.tasks = TaskManager(settings)
        app.state.catalog = catalog if catalog is not None else CatalogService(
            catalog_store_from_settings(settings),
            solve_time_limit_seconds=settings.solve_time_limit_seconds,
            solve_max_nodes=settings.solve_max_nodes,
        )
        app.state.circuit_catalog = (
            circuit_catalog
            if circuit_catalog is not None
            else CircuitCatalogService(
                circuit_catalog_store_from_settings(settings),
                solve_time_limit_seconds=settings.solve_time_limit_seconds,
                solve_max_nodes=settings.solve_max_nodes,
            )
        )
        try:
            yield
        finally:
            app.state.tasks.close()
            app.state.catalog.close()
            app.state.circuit_catalog.close()

    app = FastAPI(title="终末地解谜 API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(LimitedRecognitionUpload, max_uploads=settings.max_uploads)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return error_response(404, "NOT_FOUND", "资源不存在")
        return error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return error_response(422, "INVALID_REQUEST", "请求格式无效")

    @app.exception_handler(QueueFull)
    async def queue_full(_: Request, __: QueueFull) -> JSONResponse:
        return error_response(429, "QUEUE_FULL", "任务队列已满，请稍后重试", {"Retry-After": "5"})

    common_errors = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/api/v1/puzzles", response_model=list[PuzzleCapability])
    async def puzzles() -> list[PuzzleCapability]:
        return list(PUZZLES.values())

    def require_puzzle(puzzle_id: str) -> None:
        if puzzle_id not in PUZZLES:
            raise HTTPException(status_code=404)

    @app.post(
        "/api/v1/puzzles/balloon/recognize",
        status_code=202,
        response_model=BalloonRecognitionTaskView,
        responses={**common_errors, 408: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
                   429: {"model": ErrorResponse}},
        openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["image"], "properties": {"image": {"type": "string", "format": "binary"}}
        }}}}},
    )
    async def recognize_balloon(request: Request) -> TaskView | JSONResponse:
        try:
            async with request.form(max_files=1, max_fields=0) as form:
                image = form.get("image")
                if not isinstance(image, UploadFile) or len(form) != 1:
                    return error_response(422, "INVALID_REQUEST", "需要一个 image 图片文件")
                data = await image.read(MAX_IMAGE_BYTES + 1)
        except Exception:
            return error_response(422, "INVALID_REQUEST", "图片上传格式无效")
        if not data:
            return error_response(422, "INVALID_REQUEST", "图片文件为空")
        if len(data) > MAX_IMAGE_BYTES:
            return error_response(413, "UPLOAD_TOO_LARGE", "图片不能超过 12 MB")
        catalog_service = request.app.state.catalog
        image_sha256 = hashlib.sha256(data).hexdigest()

        def enrich(result: dict) -> dict:
            return catalog_service.enrich_recognition(result, image_sha256)

        return request.app.state.tasks.submit(recognize_balloon_job, data,
                                              settings.recognize_time_limit_seconds, finalize=enrich)

    @app.get(
        "/api/v1/puzzles/balloon/catalog/{code}",
        response_model=CatalogEntry,
        responses={**common_errors, 503: {"model": ErrorResponse}},
    )
    def balloon_catalog(code: str, request: Request) -> CatalogEntry | JSONResponse:
        # Synchronous handler: FastAPI runs it in a thread pool, so the blocking
        # database round trip never stalls the single Uvicorn event loop.
        normalized = normalize_code(code)
        if normalized is None:
            return error_response(422, "INVALID_CODE", "题号格式无效：应为 WL-A 加四位数字，例如 WL-A1001。")
        try:
            entry = request.app.state.catalog.lookup(normalized)
        except CatalogUnavailable:
            return error_response(503, "CATALOG_UNAVAILABLE", "题号目录暂时不可用，请稍后重试或改用截图识别。")
        if entry is None:
            return error_response(404, "CATALOG_NOT_FOUND", "目录中还没有这个题号的完整题面记录。")
        return entry

    @app.post(
        "/api/v1/puzzles/circuit/recognize",
        status_code=202,
        response_model=CircuitRecognitionTaskView,
        responses={**common_errors, 408: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
                   429: {"model": ErrorResponse}},
        openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["image"], "properties": {"image": {"type": "string", "format": "binary"}}
        }}}}},
    )
    async def recognize_circuit(request: Request) -> TaskView | JSONResponse:
        try:
            async with request.form(max_files=1, max_fields=0) as form:
                image = form.get("image")
                if not isinstance(image, UploadFile) or len(form) != 1:
                    return error_response(422, "INVALID_REQUEST", "需要一个 image 图片文件")
                data = await image.read(MAX_IMAGE_BYTES + 1)
        except Exception:
            return error_response(422, "INVALID_REQUEST", "图片上传格式无效")
        if not data:
            return error_response(422, "INVALID_REQUEST", "图片文件为空")
        if len(data) > MAX_IMAGE_BYTES:
            return error_response(413, "UPLOAD_TOO_LARGE", "图片不能超过 12 MB")
        catalog_service = request.app.state.circuit_catalog
        image_sha256 = hashlib.sha256(data).hexdigest()

        def enrich(result: dict) -> dict:
            return catalog_service.enrich_recognition(result, image_sha256)

        return request.app.state.tasks.submit(
            recognize_circuit_job,
            data,
            settings.recognize_time_limit_seconds,
            settings.solve_time_limit_seconds,
            settings.solve_max_nodes,
            finalize=enrich,
        )

    @app.get(
        "/api/v1/puzzles/circuit/catalog/{code}",
        response_model=CircuitCatalogEntry,
        responses={**common_errors, 503: {"model": ErrorResponse}},
    )
    def circuit_catalog_route(code: str, request: Request) -> CircuitCatalogEntry | JSONResponse:
        normalized = normalize_circuit_code(code)
        if normalized is None:
            return error_response(
                422,
                "INVALID_CODE",
                "题号格式无效：应为 V 加五位数字或 WL 加四位数字，例如 V40020 或 WL0020。",
            )
        try:
            entry = request.app.state.circuit_catalog.lookup(normalized)
        except CatalogUnavailable:
            return error_response(503, "CATALOG_UNAVAILABLE", "源石电路题号目录暂时不可用，请稍后重试或改用截图识别。")
        if entry is None:
            return error_response(404, "CATALOG_NOT_FOUND", "目录中还没有这个题号的完整题面记录。")
        return entry

    @app.post(
        "/api/v1/puzzles/{puzzle_id}/recognize",
        status_code=202,
        response_model=TaskView,
        responses={**common_errors, 501: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
        openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["image"], "properties": {"image": {"type": "string", "format": "binary"}}
        }}}}},
    )
    async def recognize(puzzle_id: str) -> JSONResponse:
        require_puzzle(puzzle_id)
        return error_response(501, "NOT_IMPLEMENTED", "此谜题的图片识别尚未开放")

    @app.post(
        "/api/v1/puzzles/balloon/solve",
        status_code=202,
        response_model=BalloonSolveTaskView,
        responses={**common_errors, 501: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    async def solve_balloon_route(payload: BalloonPuzzle, request: Request) -> TaskView:
        return request.app.state.tasks.submit(
            solve_balloon_job, payload.model_dump(), settings.solve_time_limit_seconds, settings.solve_max_nodes
        )

    @app.post(
        "/api/v1/puzzles/circuit/solve",
        status_code=202,
        response_model=CircuitSolveTaskView,
        responses={**common_errors, 429: {"model": ErrorResponse}},
    )
    async def solve_circuit_route(payload: CircuitPuzzle, request: Request) -> TaskView:
        return request.app.state.tasks.submit(
            solve_circuit_job,
            payload.model_dump(),
            settings.solve_time_limit_seconds,
            settings.solve_max_nodes,
        )

    @app.post(
        "/api/v1/puzzles/{puzzle_id}/solve",
        status_code=202,
        response_model=TaskView,
        responses={**common_errors, 501: {"model": ErrorResponse}},
    )
    async def solve(puzzle_id: str) -> JSONResponse:
        require_puzzle(puzzle_id)
        return error_response(501, "NOT_IMPLEMENTED", "此谜题的求解尚未开放")

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskView, responses=common_errors)
    async def get_task(task_id: str, request: Request) -> TaskView:
        task = request.app.state.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404)
        return task

    @app.delete("/api/v1/tasks/{task_id}", response_model=TaskView, responses=common_errors)
    async def cancel_task(task_id: str, request: Request) -> TaskView:
        task = request.app.state.tasks.cancel(task_id)
        if task is None:
            raise HTTPException(status_code=404)
        return task

    return app


app = create_app()
