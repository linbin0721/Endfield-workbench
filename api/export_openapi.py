import json
from pathlib import Path

from app.main import app


destination = Path(__file__).resolve().parent.parent / "contracts" / "openapi.json"
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(destination)
