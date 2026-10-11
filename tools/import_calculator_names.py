#!/usr/bin/env python3
"""Import small locale name maps from the numeric snapshot's exact public tables.

Raw tables stay in an ignored cache. Locale names never enter the calculation
snapshot or Worker; 64-bit localization IDs are resolved by Python, not JS.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCALES = {"zh-CN": "CN", "en": "EN", "ja": "JP", "ko": "KR"}
GENDERS = {"zh-CN": ("（男）", "（女）"), "en": (" (Male)", " (Female)"),
           "ja": ("（男性）", "（女性）"), "ko": (" (남성)", " (여성)")}
KINDS = ("characters", "weapons", "equipment", "sets")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audit(data: dict) -> None:
    provenance = read(ROOT / "web/src/i18n/game-names-provenance.json")
    if provenance["dataVersion"] != data["version"]:
        raise ValueError("Names and numeric data versions differ")
    for source in ("ItemTable", "EquipSuitTable", "I18nTextTable_CN"):
        if provenance["tables"][source]["sha256"] != data["tableHashes"][source]:
            raise ValueError(f"Names refer to different numeric source: {source}")
    for locale in LOCALES:
        path = ROOT / f"web/src/i18n/locales/{locale}/names.json"
        raw = path.read_bytes()
        if digest(raw) != provenance["outputs"][locale]["sha256"]:
            raise ValueError(f"Name file differs from provenance: {locale}")
        names = json.loads(raw)
        if set(names) != set(KINDS):
            raise ValueError(f"Incorrect name categories: {locale}")
        for kind in KINDS:
            if set(names[kind]) != {item["id"] for item in data[kind]}:
                raise ValueError(f"Incomplete or extra names: {locale}/{kind}")
            if any(not isinstance(name, str) or not name.strip() or "<" in name
                   for name in names[kind].values()):
                raise ValueError(f"Invalid localized names: {locale}/{kind}")
    print(json.dumps({"verified": True, "locales": list(LOCALES),
                      "counts": {kind: len(data[kind]) for kind in KINDS}}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, help="Ignored raw TableCfg directory")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--audit", action="store_true", help="Offline coverage/version/hash audit")
    args = parser.parse_args()
    data = read(ROOT / "web/src/calculator/data.json")
    if args.audit:
        audit(data)
        return
    if args.cache is None:
        parser.error("--cache required for name import")
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    base = f"https://data.akedata.wiki/public/{data['version']}/TableCfg/"
    tables = ["ItemTable", "EquipSuitTable"] + [f"I18nTextTable_{code}" for code in LOCALES.values()]
    if args.download:
        def download(table: str) -> None:
            path = cache / f"{table}.json"
            if path.exists():
                # Existing trusted cache is checked against the pinned table hashes below.
                return
            request = Request(base + table + ".json", headers={
                "User-Agent": "Mozilla/5.0", "Referer": "https://www.akedata.wiki/"})
            with urlopen(request, timeout=45) as response:
                raw = response.read(32 * 1024 * 1024 + 1)
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError(f"Oversized localization table: {table}")
            json.loads(raw)
            path.write_bytes(raw)
            print(f"Downloaded {table}: {len(raw)} bytes", flush=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(download, tables))
    raw_tables = {name: (cache / f"{name}.json").read_bytes() for name in tables}
    for name in ("ItemTable", "EquipSuitTable", "I18nTextTable_CN"):
        if digest(raw_tables[name]) != data["tableHashes"][name]:
            raise ValueError(f"Source differs from pinned numeric snapshot: {name}")
    item_table = json.loads(raw_tables["ItemTable"])
    suit_table = json.loads(raw_tables["EquipSuitTable"])
    maps = {}
    for locale, code in LOCALES.items():
        texts = json.loads(raw_tables[f"I18nTextTable_{code}"])
        localized = {kind: {} for kind in KINDS}
        for kind in KINDS:
            for item in data[kind]:
                if kind == "sets":
                    references = [effect["suitName"] for effect in suit_table[item["id"]]["list"]]
                    values = {texts.get(str(ref["id"]), "") for ref in references}
                    values.discard("")
                    if len(values) != 1:
                        raise ValueError(f"Missing/ambiguous set name: {locale}/{item['id']}")
                    name = values.pop()
                else:
                    ref = item_table[item["id"]]["name"]
                    name = texts.get(str(ref["id"]), "")
                if not isinstance(name, str) or not name.strip() or "<" in name:
                    raise ValueError(f"Missing or invalid name: {locale}/{item['id']}")
                if kind == "characters" and item["id"] in ("chr_0002_endminm", "chr_0003_endminf"):
                    name += GENDERS[locale][int(item["id"].endswith("f"))]
                localized[kind][item["id"]] = name
                if locale == "zh-CN" and name != item["name"]:
                    raise ValueError(f"Chinese name changes existing display: {item['id']}")
        maps[locale] = localized
    outputs = {}
    for locale, names in maps.items():
        path = ROOT / f"web/src/i18n/locales/{locale}/names.json"
        write(path, names)
        raw = path.read_bytes()
        outputs[locale] = {"sha256": digest(raw), "size": len(raw)}
    write(ROOT / "web/src/i18n/game-names-provenance.json", {
        "schemaVersion": 1, "dataVersion": data["version"], "source": data["source"],
        "retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": {name: {"url": base + name + ".json", "sha256": digest(raw), "size": len(raw)}
                   for name, raw in raw_tables.items()},
        "outputs": outputs, "annotation": "Administrator gender suffixes are display disambiguators",
    })
    audit(data)


if __name__ == "__main__":
    main()
