#!/usr/bin/env python3
"""Import/audit presentation assets separately from the calculator's numeric snapshot.

Default is an offline audit. --refresh explicitly downloads the current public asset
index and the snapshot's exact ItemTable, verifies source hashes, then replaces the
media lock/registry and referenced icons. Raw sources stay in --cache (Git ignored).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
from urllib.request import Request, urlopen

from PIL import Image, __version__ as pillow_version, features

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "web/src/calculator/media"
INDEX_URL = "https://data.akedata.wiki/asset-sync-index.json"
IMAGE_BASE = "https://data.akedata.wiki/public/images/"
KINDS = {"characters": "v3_character", "weapons": "v3_weapon", "equipment": "v3_item"}
ENCODING = {"format": "webp", "maxEdge": 192, "quality": 88, "method": 6}
SAFE_ID = re.compile(r"[a-zA-Z0-9_]+\Z")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fetch(url: str, limit: int = 32 * 1024 * 1024) -> bytes:
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "EndfieldWorkbench-media/1.0",
                                           "Referer": "https://www.akedata.wiki/"})
            with urlopen(request, timeout=30) as response:
                raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError(f"Source exceeds download limit: {url}")
            return raw
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("Unreachable")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def detail_url(kind: str, entity_id: str) -> str:
    if not SAFE_ID.fullmatch(entity_id):
        raise ValueError(f"Invalid game id: {entity_id}")
    return f"https://www.akedata.wiki/?plugin={KINDS[kind]}&id={entity_id}"


def plan(data: dict, items: dict, index: dict) -> tuple[dict, dict]:
    entities = {kind: {} for kind in KINDS}
    assets = {}
    indexed = index["datasets"]["images"]["files"]
    for kind in KINDS:
        for item in data[kind]:
            entity_id = item["id"]
            detail = detail_url(kind, entity_id)
            # The fixed ItemTable supplies aliases; item IDs are not icon IDs.
            icon_id = entity_id if kind == "characters" else items[entity_id]["iconId"]
            if not SAFE_ID.fullmatch(icon_id):
                raise ValueError(f"Invalid icon id: {icon_id}")
            subpath = (f"charremoteicon/icon_{entity_id}.png" if kind == "characters"
                       else f"itemiconbig/{icon_id}.png")
            source_path = f"assets/beyond/dynamicassets/gameplay/ui/sprites/{subpath}"
            record = indexed[source_path]  # Missing assets fail rather than guessing.
            output = f"icons/{kind}/{icon_id}.webp"
            entities[kind][entity_id] = {"name": item["name"], "iconId": icon_id,
                                        "file": output, "detailUrl": detail}
            asset = {"file": output, "sourcePath": source_path,
                     "sourceUrl": IMAGE_BASE + source_path, "sourceMd5": record["md5"],
                     "sourceSize": record["size"], "sourceVersion": record["version"]}
            if output in assets and assets[output] != asset:
                raise ValueError(f"Conflicting icon aliases: {output}")
            assets[output] = asset
    return entities, assets


def refresh(data: dict, cache: Path) -> None:
    if pillow_version != "12.3.0":
        raise ValueError("Use tools/requirements-media.txt to lock the image encoder")
    cache.mkdir(parents=True, exist_ok=True)
    table_url = f"https://data.akedata.wiki/public/{data['version']}/TableCfg/ItemTable.json"
    table_raw = fetch(table_url)
    if sha256(table_raw) != data["tableHashes"]["ItemTable"]:
        raise ValueError("ItemTable differs from the calculator's locked numeric source")
    index_raw = fetch(INDEX_URL)
    index = json.loads(index_raw)
    (cache / "asset-sync-index.json").write_bytes(index_raw)
    (cache / "ItemTable.json").write_bytes(table_raw)
    entities, planned = plan(data, json.loads(table_raw), index)
    originals = cache / "originals"
    originals.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="media-stage-", dir=cache) as temp:
        stage = Path(temp)

        def convert(asset: dict) -> dict:
            expected_md5 = asset["sourceMd5"]
            if not re.fullmatch(r"[a-f0-9]{32}", expected_md5):
                raise ValueError("Invalid source MD5")
            source = originals / f"{expected_md5}.png"
            raw = source.read_bytes() if source.exists() else fetch(asset["sourceUrl"], 8 * 1024 * 1024)
            if len(raw) != asset["sourceSize"] or hashlib.md5(raw).hexdigest() != expected_md5:
                raise ValueError(f"Source changed since index: {asset['sourcePath']}")
            if not source.exists():
                source.write_bytes(raw)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != "PNG" or max(image.size) > 2048 or min(image.size) < 1:
                    raise ValueError(f"Unexpected source image: {asset['sourcePath']}")
                original_width, original_height = image.size
                image = image.convert("RGBA")
                image.thumbnail((ENCODING["maxEdge"], ENCODING["maxEdge"]), Image.Resampling.LANCZOS)
                out = stage / asset["file"]
                out.parent.mkdir(parents=True, exist_ok=True)
                image.save(out, "WEBP", quality=ENCODING["quality"], method=ENCODING["method"], exact=True)
                encoded = out.read_bytes()
                return {**asset, "sourceSha256": sha256(raw),
                        "sourceWidth": original_width, "sourceHeight": original_height,
                        "sha256": sha256(encoded), "size": len(encoded),
                        "width": image.width, "height": image.height}

        # Small bounded concurrency; no production OCR/model processes are started.
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(convert, asset)
                       for asset in sorted(planned.values(), key=lambda a: a["file"])]
            try:
                assets = [future.result() for future in futures]
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
        registry = {kind: {key: {"file": value["file"], "detailUrl": value["detailUrl"]}
                           for key, value in records.items()} for kind, records in entities.items()}
        lock = {"schemaVersion": 1, "dataVersion": data["version"],
                "retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": {"name": "AKEndfield Wiki / AKEData", "website": "https://www.akedata.wiki/",
                           "indexUrl": INDEX_URL, "indexRevision": index["revision"],
                           "indexSha256": sha256(index_raw), "itemTableUrl": table_url,
                           "itemTableSha256": sha256(table_raw)},
                "rights": {"owner": "Hypergryph and related rights holders",
                           "status": "No image-specific redistribution licence independently confirmed",
                           "usage": "Unofficial player tool; source attribution is not proof of permission",
                           "guidelinesUrl": "https://endfield.gryphline.com/en-us/news/4497"},
                "encoding": {**ENCODING, "pillow": pillow_version,
                             "libwebp": features.version("webp")},
                "entities": entities, "assets": assets}
        # Install only after every source has passed verification and conversion.
        for asset in assets:
            target = MEDIA / asset["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / asset["file"], target)
        write_json(MEDIA / "registry.json", registry)
        write_json(MEDIA / "provenance.json", lock)
    audit(data)


def audit(data: dict) -> None:
    lock = json.loads((MEDIA / "provenance.json").read_text(encoding="utf-8"))
    registry = json.loads((MEDIA / "registry.json").read_text(encoding="utf-8"))
    if lock["dataVersion"] != data["version"]:
        raise ValueError("Media/numeric data version mismatch; review and refresh the mapping")
    if lock["source"]["itemTableSha256"] != data["tableHashes"]["ItemTable"]:
        raise ValueError("Media/numeric ItemTable mismatch")
    assets = {asset["file"]: asset for asset in lock["assets"]}
    if len(assets) != len(lock["assets"]) or set(registry) != set(KINDS):
        raise ValueError("Duplicate asset or invalid media kinds")
    referenced = set()
    for kind in KINDS:
        ids = {entry["id"] for entry in data[kind]}
        if set(registry[kind]) != ids or set(lock["entities"][kind]) != ids:
            raise ValueError(f"Incomplete/extra {kind} mapping")
        for item in data[kind]:
            entry = lock["entities"][kind][item["id"]]
            expected = {key: entry[key] for key in ("file", "detailUrl")}
            if registry[kind][item["id"]] != expected or entry["name"] != item["name"]:
                raise ValueError(f"Registry/provenance mismatch: {item['id']}")
            if entry["detailUrl"] != detail_url(kind, item["id"]) or entry["file"] not in assets:
                raise ValueError(f"Invalid detail link/file: {item['id']}")
            expected_file = f"icons/{kind}/{entry['iconId']}.webp"
            subpath = (f"charremoteicon/icon_{item['id']}.png" if kind == "characters"
                       else f"itemiconbig/{entry['iconId']}.png")
            expected_source = f"assets/beyond/dynamicassets/gameplay/ui/sprites/{subpath}"
            if entry["file"] != expected_file or assets[entry["file"]]["sourcePath"] != expected_source:
                raise ValueError(f"Incorrect icon association: {item['id']}")
            referenced.add(entry["file"])
    actual = {path.relative_to(MEDIA).as_posix() for path in (MEDIA / "icons").rglob("*.webp")}
    if actual != referenced or referenced != set(assets):
        raise ValueError("Unexpected/unreferenced/missing media files; review before removing any old assets")
    for file, asset in assets.items():
        path = PurePosixPath(file)
        if path.is_absolute() or ".." in path.parts or path.parts[0] != "icons":
            raise ValueError(f"Invalid local asset path: {file}")
        raw = (MEDIA / file).read_bytes()
        if len(raw) != asset["size"] or sha256(raw) != asset["sha256"]:
            raise ValueError(f"Local asset hash mismatch: {file}")
        if asset["sourceUrl"] != IMAGE_BASE + asset["sourcePath"]:
            raise ValueError(f"Unexpected source: {file}")
        if not re.fullmatch(r"[a-f0-9]{64}", asset["sourceSha256"]):
            raise ValueError(f"Invalid source hash: {file}")
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            if image.format != "WEBP" or image.size != (asset["width"], asset["height"]):
                raise ValueError(f"Invalid image: {file}")
            if max(image.size) > ENCODING["maxEdge"]:
                raise ValueError(f"Oversized icon: {file}")
    counts = {kind: len(registry[kind]) for kind in KINDS}
    print(json.dumps({"verified": True, "counts": counts, "files": len(assets),
                      "sourceBytes": sum(a["sourceSize"] for a in assets.values()),
                      "iconBytes": sum(a["size"] for a in assets.values())}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Explicitly download and replace the media lock")
    parser.add_argument("--cache", type=Path, help="Ignored directory for raw data/images and staging")
    args = parser.parse_args()
    if args.refresh and args.cache is None:
        parser.error("--refresh requires --cache (keep original assets outside Git)")
    data = json.loads((ROOT / "web/src/calculator/data.json").read_text(encoding="utf-8"))
    if args.refresh:
        refresh(data, args.cache.resolve())
    else:
        audit(data)


if __name__ == "__main__":
    main()
