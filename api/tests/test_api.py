from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tasks import QueueFull


def make_client() -> TestClient:
    return TestClient(create_app(Settings(cors_origins=("http://localhost:5173",), max_workers=1)))


def test_health_capabilities_and_unavailable_engines() -> None:
    with make_client() as client:
        assert client.get("/api/v1/health").json() == {"status": "ok"}
        puzzles = client.get("/api/v1/puzzles").json()
        assert {p["id"] for p in puzzles} == {"balloon", "circuit"}
        by_id = {p["id"]: p for p in puzzles}
        assert by_id["balloon"]["recognition_available"] and by_id["balloon"]["solving_available"]
        assert by_id["balloon"]["supported_rule_versions"] == ["center-torque-v1"]
        assert not by_id["circuit"]["recognition_available"] and not by_id["circuit"]["solving_available"]
        assert by_id["circuit"]["supported_rule_versions"] == []
        # Concrete circuit routes are callable for C2 integration while the
        # public capability remains disabled until the D2 frontend is ready.
        recognition = client.post("/api/v1/puzzles/circuit/recognize")
        assert recognition.status_code == 422
        assert recognition.json()["error"]["code"] == "INVALID_REQUEST"
        solving = client.post("/api/v1/puzzles/circuit/solve", json={})
        assert solving.status_code == 422
        assert solving.json()["error"]["code"] == "INVALID_REQUEST"
        assert client.post("/api/v1/puzzles/circuit/solve", content=b"invalid").status_code == 422
        assert client.post("/api/v1/puzzles/unknown/recognize").status_code == 404
        assert client.get("/api/v1/tasks/missing").json() == {"error": {"code": "NOT_FOUND", "message": "资源不存在"}}
        assert client.get("/api/v1/unknown").json()["error"]["code"] == "NOT_FOUND"


def test_cors_exact_origin() -> None:
    with make_client() as client:
        allowed = client.options("/api/v1/puzzles", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"
        })
        denied = client.options("/api/v1/puzzles", headers={
            "Origin": "https://other.example", "Access-Control-Request-Method": "GET"
        })
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert denied.status_code == 400
        assert "access-control-allow-origin" not in denied.headers


def test_openapi_describes_contract() -> None:
    with make_client() as client:
        schema = client.get("/openapi.json").json()
        assert "multipart/form-data" in schema["paths"]["/api/v1/puzzles/{puzzle_id}/recognize"]["post"]["requestBody"]["content"]
        assert "application/json" in schema["paths"]["/api/v1/puzzles/balloon/solve"]["post"]["requestBody"]["content"]
        assert "BalloonPuzzle" in schema["components"]["schemas"]
        assert "BalloonSolveResult" in schema["components"]["schemas"]
        assert "BalloonRecognitionResult" in schema["components"]["schemas"]
        assert "multipart/form-data" in schema["paths"]["/api/v1/puzzles/balloon/recognize"]["post"]["requestBody"]["content"]
        assert schema["components"]["schemas"]["TaskView"]["properties"]["status"]


def test_queue_full_maps_to_retryable_error() -> None:
    app = create_app(Settings())

    @app.get("/test-only-queue-full", include_in_schema=False)
    def test_only_queue_full() -> None:
        raise QueueFull()

    with TestClient(app) as client:
        response = client.get("/test-only-queue-full")
        assert response.status_code == 429
        assert response.headers["retry-after"] == "5"
        assert response.json()["error"]["code"] == "QUEUE_FULL"
