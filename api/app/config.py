from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    max_workers: int = 2
    max_queued: int = 8
    result_ttl_seconds: int = 900
    max_retained: int = 100
    solve_time_limit_seconds: float = 3.0
    solve_max_nodes: int = 300000
    recognize_time_limit_seconds: float = 25.0
    max_uploads: int = 2
    catalog_db_host: str | None = None
    catalog_db_port: int = 5432
    catalog_db_name: str | None = None
    catalog_db_user: str | None = None
    catalog_db_password: str | None = None
    catalog_db_timeout_seconds: float = 3.0

    def __post_init__(self) -> None:
        if self.max_workers < 1 or self.max_queued < 0:
            raise ValueError("MAX_WORKERS must be positive and MAX_QUEUED nonnegative")
        if self.result_ttl_seconds < 1 or self.max_retained < 1:
            raise ValueError("RESULT_TTL_SECONDS and MAX_RETAINED must be positive")
        if not self.cors_origins or any(not origin.startswith(("http://", "https://")) for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must contain explicit HTTP origins")
        if not 0 < self.solve_time_limit_seconds <= 10 or not 1 <= self.solve_max_nodes <= 1_000_000:
            raise ValueError("solver limits must be positive and within service caps")
        if not 0 < self.recognize_time_limit_seconds <= 30 or not 1 <= self.max_uploads <= 8:
            raise ValueError("recognition limits must be positive and within service caps")
        if not 1 <= self.catalog_db_port <= 65535 or not 0 < self.catalog_db_timeout_seconds <= 10:
            raise ValueError("catalog database settings must be within service caps")


def load_settings() -> Settings:
    origins = tuple(x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip())
    return Settings(
        cors_origins=origins,
        max_workers=int(os.getenv("MAX_WORKERS", "2")),
        max_queued=int(os.getenv("MAX_QUEUED", "8")),
        result_ttl_seconds=int(os.getenv("RESULT_TTL_SECONDS", "900")),
        max_retained=int(os.getenv("MAX_RETAINED", "100")),
        solve_time_limit_seconds=float(os.getenv("SOLVE_TIME_LIMIT_SECONDS", "3")),
        solve_max_nodes=int(os.getenv("SOLVE_MAX_NODES", "300000")),
        recognize_time_limit_seconds=float(os.getenv("RECOGNIZE_TIME_LIMIT_SECONDS", "25")),
        max_uploads=int(os.getenv("MAX_UPLOADS", "2")),
        catalog_db_host=os.getenv("CATALOG_DB_HOST") or None,
        catalog_db_port=int(os.getenv("CATALOG_DB_PORT", "5432")),
        catalog_db_name=os.getenv("CATALOG_DB_NAME") or None,
        catalog_db_user=os.getenv("CATALOG_DB_USER") or None,
        catalog_db_password=os.getenv("CATALOG_DB_PASSWORD") or None,
        catalog_db_timeout_seconds=float(os.getenv("CATALOG_DB_TIMEOUT_SECONDS", "3")),
    )
