#!/usr/bin/env python3
"""Normalize a pinned public TableCfg snapshot; never ship raw localization IDs.

Usage: python3 tools/import_calculator_data.py --cache /path/to/TableCfg
Use --download to fetch the pinned version into that cache first.
"""
import argparse
import hashlib
import json
import pathlib
import re
import urllib.request

VERSION = "1.5.3/10506507-7"
BASE = f"https://data.akedata.wiki/public/{VERSION}/TableCfg/"
TABLES = ["CharacterTable", "CharGrowthTable", "CharBreakTable", "CharacterPotentialTable",
          "PotentialTalentEffectTable", "ItemTable", "I18nTextTable_CN", "EquipTable",
          "EquipSuitTable", "SkillPatchTable", "WeaponBasicTable",
          "WeaponBreakThroughTemplateTable", "WeaponTalentTemplateTable"]
ATTRS = {"str": 39, "agi": 40, "wisd": 41, "will": 42, "mainattr": -1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=pathlib.Path, required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        args.cache.mkdir(parents=True, exist_ok=True)
        for name in TABLES:
            request = urllib.request.Request(BASE + name + ".json", headers={
                "User-Agent": "Mozilla/5.0", "Referer": "https://www.akedata.wiki/"})
            with urllib.request.urlopen(request, timeout=60) as response:
                (args.cache / (name + ".json")).write_bytes(response.read())
    tables = {name: json.loads((args.cache / (name + ".json")).read_text()) for name in TABLES}
    texts, items, skills = (tables[n] for n in ["I18nTextTable_CN", "ItemTable", "SkillPatchTable"])
    max_level = max(row["maxLevel"] for row in tables["CharBreakTable"].values())

    def text(ref):
        return texts.get(str(ref.get("id", 0)), ref.get("text", ""))

    def name(key):
        return text(items[key]["name"])

    def modifiers(rows):
        result = []
        for m in rows:
            if m.get("modifyAttributeType", 0) or 39 <= m["attrType"] <= 42:
                # Fail on new semantics; the importer is an explicit compatibility gate.
                assert m["modifierType"] in [5, 6], m
                values = m.get("attrValues", [m.get("attrValue", 0)])
                assert all(v >= 0 for v in values), m
                if m["modifierType"] == 5:
                    assert all(v == int(v) for v in values), m
                result.append({"attribute": m["attrType"] - 39,
                               "scope": m.get("modifyAttributeType", 0),
                               "stage": "flat" if m["modifierType"] == 5 else "percent",
                               "values": values,
                               "index": m.get("attrIndex", 0)})
        return result

    def permanent_effect(effect_id):
        effect = tables["PotentialTalentEffectTable"].get(effect_id, {})
        return modifiers([e["attrModifier"] for e in effect.get("dataList", [])
                          if e["modifyType"] == 4 and not e["activeCondition"]])

    characters = []
    for key, c in tables["CharacterTable"].items():
        if key == "chr_9000_endmin":
            continue
        growth = tables["CharGrowthTable"][key]
        levels = {}
        for row in c["attributes"]:
            attrs = {a["attrType"]: a["attrValue"] for a in row["Attribute"]["attrs"]}
            level = int(attrs[0])
            if level > max_level:
                continue
            if level not in levels or levels[level]["breakStage"] < row["breakStage"]:
                levels[level] = {"level": level, "breakStage": row["breakStage"],
                                 "base": [attrs[a] for a in range(39, 43)]}
        nodes, passives = [], []
        for node in growth["talentNodeMap"].values():
            if node["nodeType"] == 3:
                info = node["attributeNodeInfo"]
                nodes.append({"breakStage": info["breakStage"],
                              "modifiers": modifiers(info["attributeModifiers"])})
            elif node["nodeType"] == 4:
                info = node["passiveSkillNodeInfo"]
                mods = permanent_effect(info["talentEffectId"])
                if mods:
                    passives.append({"breakStage": info["breakStage"], "index": info["index"],
                                     "level": info["level"], "modifiers": mods})
        potentials = [{"level": row["level"], "modifiers": permanent_effect(row["potentialEffectId"])}
                      for row in tables["CharacterPotentialTable"][key]["potentialUnlockBundle"]]
        label = name(key)
        if key in ["chr_0002_endminm", "chr_0003_endminf"]:
            label += "（男）" if key.endswith("m") else "（女）"
        characters.append({"id": key, "name": label, "weaponType": c["weaponType"],
                           "main": c["mainAttrType"] - 39, "sub": c["subAttrType"] - 39,
                           "maxLevel": max_level, "levels": list(levels.values()), "nodes": nodes,
                           "passives": passives, "potentials": potentials,
                           "tiers": [{"breakStage": v["breakStage"], "tier": v["equipTierLimit"]}
                                     for v in growth["charBreakCostMap"].values()]})
    equipment = []
    for key, e in tables["EquipTable"].items():
        equipment.append({"id": key, "name": name(key), "slot": e["partType"],
                          "minLevel": e["minWearLv"], "tier": items[key]["rarity"],
                          "set": e["suitID"], "modifiers": modifiers(e["equipAttrModifiers"])})
    sets = []
    for key, suit in tables["EquipSuitTable"].items():
        for effect in suit["list"]:
            row = next(r for r in skills[effect["skillID"]]["SkillPatchDataBundle"]
                       if r["level"] == effect["skillLv"])
            prefix = re.split(r"[。\n]", text(row["description"]))[0]
            mods = []
            for bb in row["blackboard"]:
                if bb["key"] in ["str_up", "agi_up", "wisd_up", "will_up"]:
                    attribute = ATTRS[bb["key"].removesuffix("_up")] - 39
                    if ["力量", "敏捷", "智识", "意志"][attribute] in prefix:
                        mods.append({"attribute": attribute, "scope": 0, "stage": "flat",
                                     "values": [bb["value"]], "index": 0})
            if mods:
                sets.append({"id": key, "name": text(effect["suitName"]),
                             "pieces": effect["equipCnt"], "modifiers": mods})
    weapons = []
    for key, w in tables["WeaponBasicTable"].items():
        bounds = tables["WeaponBreakThroughTemplateTable"][w["breakthroughTemplateId"]]["list"][-1]["skillLevelBounds"]
        first = skills[w["weaponSkillList"][0]]["SkillPatchDataBundle"]
        assert all(len(r["blackboard"]) == 1 and r["blackboard"][0]["key"] in ATTRS for r in first)
        bbkey = first[0]["blackboard"][0]["key"]
        passive = []
        passive_scope = 0
        for skill_id in w["weaponSkillList"][1:]:
            for row in skills[skill_id]["SkillPatchDataBundle"]:
                desc = text(row["description"])
                # Only the unconditional first sentence. Conditional all_attr_up (负山) is excluded.
                prefix = re.split(r"[。\n]", desc)[0]
                prefix = re.sub(r"<[^>]*>", "", prefix)
                for bb in row["blackboard"]:
                    if bb["key"] in ["primary_attr_up", "second_attr_up", "all_attr_up"]:
                        scope = (1 if prefix.startswith("主能力") else
                                 2 if prefix.startswith("副能力") else
                                 3 if prefix.startswith("全能力") else 0)
                        if scope:
                            assert skill_id == w["weaponSkillList"][-1], key
                            passive_scope = scope
                            passive.append({"level": row["level"], "value": bb["value"]})
        weapons.append({"id": key, "name": name(key), "type": w["weaponType"],
                        "rarity": w["rarity"], "level": w["maxLv"],
                        "attribute": ATTRS[bbkey] - 39 if bbkey != "mainattr" else -1,
                        "first": [{"level": r["level"], "value": r["blackboard"][0]["value"]} for r in first],
                        "bounds": bounds, "passiveScope": passive_scope, "passive": passive,
                        "refine": tables["WeaponTalentTemplateTable"][w["talentTemplateId"]]["list"]})
    hashes = {n: hashlib.sha256((args.cache / (n + ".json")).read_bytes()).hexdigest() for n in TABLES}
    result = {"schemaVersion": 1, "rulesVersion": "persistent-panel-v1", "version": VERSION,
              "source": "https://www.akedata.wiki/", "sourceUpdatedAt": "2026-09-24",
              "tableHashes": hashes, "characters": characters, "equipment": equipment,
              "sets": sets, "weapons": weapons}
    destination = pathlib.Path(__file__).resolve().parents[1] / "web/src/calculator/data.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{len(characters)} operators, {len(weapons)} weapons, {len(equipment)} equipment, {len(sets)} stat sets; {destination.stat().st_size} bytes")


if __name__ == "__main__":
    main()
