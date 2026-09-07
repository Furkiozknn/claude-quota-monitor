"""Kotayi ne tuketti? — yerel transcript'lerden atif.

Panonun gosterdigi yuzde resmi ve dogru, ama tek basina eksik: "5 saatlik
pencerem %60 dolu" bilgisi "peki bunu ne yedi?" sorusunu cevaplamiyor.

Bu modul `~/.claude/projects/<slug>/<session>.jsonl` dosyalarini okuyup
belirli bir zaman araligindaki token tuketimini projeye, modele ve oturuma
gore dagitir. Boylece pano su cumleyi kurabiliyor:

    "5 saatlik pencerenin %60'i doldu — %48'i D:\\Claude Projeleri'nden."

Sinirlar (durustce)
-------------------
* Bu bir **oran tahmini**, kesin atif degil. Anthropic pencere yuzdesinin
  hangi tokenlardan geldigini soylemiyor; biz yerel token sayilarinin
  payini hesaplayip yuzdeyi o oranda bolusuyoruz.
* Transcript'te gorunmeyen kullanim (baska cihaz, claude.ai web, mobil)
  buraya yansimaz. Toplam yerel token, pencereyi dolduran her seyi
  temsil etmeyebilir — pano bunu ayrica belirtir.
* Yalnizca okur. Transcript dosyalarina asla yazmaz.

Bagimlilik yok.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Ayni sorgu tekrar tekrar gelirse dosyalari yeniden taramayalim.
_CACHE: dict = {"since": None, "at": 0.0, "value": None}
CACHE_TTL = 30.0


def _iso_to_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def _pretty_project(slug: str, cwds: dict[str, int]) -> str:
    """Klasor slug'i yerine en sik gorulen gercek cwd'yi goster."""
    if cwds:
        return max(cwds.items(), key=lambda kv: kv[1])[0]
    return slug


def scan(since: float, until: float | None = None) -> dict:
    """[since, until] araligindaki token tuketimini dagitir.

    Doner: {"projects": [...], "models": [...], "sessions": [...],
            "totals": {...}, "scanned_files": int, "partial": bool}
    """
    until = until or time.time()

    cached = _CACHE
    if (cached["value"] is not None and cached["since"] == round(since)
            and time.time() - cached["at"] < CACHE_TTL):
        return cached["value"]

    projects: dict[str, dict] = defaultdict(
        lambda: {"tokens": 0, "output": 0, "cache_read": 0, "turns": 0,
                 "cwds": defaultdict(int)})
    models: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "turns": 0})
    sessions: dict[str, dict] = defaultdict(
        lambda: {"tokens": 0, "turns": 0, "project": "", "last": 0.0})

    totals = {"tokens": 0, "input": 0, "output": 0,
              "cache_read": 0, "cache_creation": 0, "turns": 0}
    scanned = 0
    partial = False

    if not PROJECTS_DIR.is_dir():
        return {"projects": [], "models": [], "sessions": [], "totals": totals,
                "scanned_files": 0, "partial": True,
                "note": "~/.claude/projects bulunamadı."}

    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        for path in proj_dir.glob("*.jsonl"):
            try:
                # Dosya araliktan once son kez degistiyse hic acmaya gerek yok
                if path.stat().st_mtime < since:
                    continue
            except OSError:
                continue

            scanned += 1
            try:
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        # Ucuz on eleme: JSON ayristirmadan once metin kontrolu
                        if '"usage"' not in line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("type") != "assistant":
                            continue

                        ts = _iso_to_epoch(rec.get("timestamp"))
                        if ts is None or ts < since or ts > until:
                            continue

                        msg = rec.get("message") or {}
                        usage = msg.get("usage") or {}
                        inp = int(usage.get("input_tokens") or 0)
                        out = int(usage.get("output_tokens") or 0)
                        cread = int(usage.get("cache_read_input_tokens") or 0)
                        ccreate = int(usage.get("cache_creation_input_tokens") or 0)

                        # "Agirlik" olarak girdi+cikti+cache olusturma alindi.
                        # Cache OKUMA agirliga katilmiyor: ucuz olan o ve
                        # pencereyi doldurmadaki payi cok daha dusuk.
                        weight = inp + out + ccreate

                        slug = proj_dir.name
                        p = projects[slug]
                        p["tokens"] += weight
                        p["output"] += out
                        p["cache_read"] += cread
                        p["turns"] += 1
                        cwd = rec.get("cwd")
                        if cwd:
                            p["cwds"][cwd] += 1

                        model = msg.get("model") or "bilinmiyor"
                        models[model]["tokens"] += weight
                        models[model]["turns"] += 1

                        sid = rec.get("sessionId") or "?"
                        s = sessions[sid]
                        s["tokens"] += weight
                        s["turns"] += 1
                        s["project"] = slug
                        s["last"] = max(s["last"], ts)

                        totals["tokens"] += weight
                        totals["input"] += inp
                        totals["output"] += out
                        totals["cache_read"] += cread
                        totals["cache_creation"] += ccreate
                        totals["turns"] += 1
            except OSError:
                partial = True
                continue

    toplam = totals["tokens"] or 1

    proj_list = [{
        "key": slug,
        "label": _pretty_project(slug, d["cwds"]),
        "tokens": d["tokens"],
        "share": round(100.0 * d["tokens"] / toplam, 1),
        "turns": d["turns"],
        "output": d["output"],
        "cache_read": d["cache_read"],
    } for slug, d in projects.items()]
    proj_list.sort(key=lambda x: -x["tokens"])

    model_list = [{
        "key": m, "tokens": d["tokens"], "turns": d["turns"],
        "share": round(100.0 * d["tokens"] / toplam, 1),
    } for m, d in models.items()]
    model_list.sort(key=lambda x: -x["tokens"])

    sess_list = [{
        "key": sid[:8], "tokens": d["tokens"], "turns": d["turns"],
        "project": d["project"], "last": d["last"],
        "share": round(100.0 * d["tokens"] / toplam, 1),
    } for sid, d in sessions.items()]
    sess_list.sort(key=lambda x: -x["tokens"])

    result = {
        "since": since,
        "until": until,
        "projects": proj_list,
        "models": model_list,
        "sessions": sess_list[:10],
        "totals": totals,
        "scanned_files": scanned,
        "partial": partial,
    }

    _CACHE.update(since=round(since), at=time.time(), value=result)
    return result


if __name__ == "__main__":  # elle deneme: son 5 saat
    import sys
    data = scan(time.time() - 5 * 3600)
    print(f"taranan dosya: {data['scanned_files']}  tur: {data['totals']['turns']}")
    print(f"toplam agirlik: {data['totals']['tokens']:,} token")
    print("\nprojeler:")
    for p in data["projects"]:
        print(f"  %{p['share']:5.1f}  {p['tokens']:>10,}  {p['turns']:>4} tur  {p['label']}")
    print("\nmodeller:")
    for m in data["models"]:
        print(f"  %{m['share']:5.1f}  {m['tokens']:>10,}  {m['key']}")
    sys.exit(0)
