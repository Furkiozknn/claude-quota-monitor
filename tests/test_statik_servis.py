"""Statik dosya servisinin sinirlari — gercekten yasanmis iki hataya karsilik gelir.

1. Yol gecisi: eski surum `(WEB_DIR / rel).resolve()` ile bir yol uretiyordu.
   Duzeltmeden once bir donem oneki duz string olarak karsilastiriliyordu ve
   `web` klasorunun kardesi `web-yedek` onekten geciyordu. Sonraki surum
   `is_relative_to` ile dogruydu ama CodeQL uc ayri py/path-injection bulgusu
   acti, cunku dogrulugu cikarim gerektiriyordu.

2. Simdiki surum istek yolunu hicbir zaman bir yol parcasina cevirmiyor:
   WEB_DIR altindaki gercek dosyalarin haritasinda ARIYOR. Bu testler o
   sozlesmeyi sabitler - haritada olmayan hicbir sey servis edilmez.

Calistirma:  python -m pytest tests/test_statik_servis.py
"""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


class SahtePoller:
    """Ag'a cikmayan poller: testler tek bir HTTP sorgusu bile uretmemeli."""

    def __init__(self) -> None:
        self.durtme = 0

    def snapshot(self) -> dict:
        return {"cards": [], "raw": {}, "subscription": "test"}

    def poke(self) -> None:
        self.durtme += 1


@pytest.fixture(scope="module")
def sunucu():
    poller = SahtePoller()
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(poller, conn))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    conn.close()


def _durum(taban: str, yol: str) -> int:
    try:
        with urllib.request.urlopen(taban + yol, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_web_klasorundeki_dosyalar_servis_ediliyor(sunucu):
    for yol in ("/", "/index.html", "/app.js", "/style.css"):
        assert _durum(sunucu, yol) == 200, yol


# Her biri, istek yolunun bir yol parcasina cevrilmesi halinde WEB_DIR
# disina cikabilecek bir bicim. Hicbiri haritada olmadigi icin hepsi 404.
@pytest.mark.parametrize(
    "yol",
    [
        "/../server.py",
        "/../../etc/passwd",
        "/./../server.py",
        "/web/../server.py",
        "/subdir/../../server.py",
        "//etc/passwd",
        "/C:/Windows/win.ini",
        "/%2e%2e/server.py",
        "/..%2fserver.py",
        "/yok.html",
    ],
)
def test_harita_disindaki_hicbir_sey_servis_edilmiyor(sunucu, yol):
    assert _durum(sunucu, yol) == 404


def test_harita_sadece_web_klasorunu_iceriyor():
    harita = server._servilebilir_dosyalar()
    kok = server.WEB_DIR.resolve()
    assert harita, "web/ klasoru bos gorunuyor - test ortami bozuk"
    for adres, yol in harita.items():
        assert yol.resolve().is_relative_to(kok), adres
        assert ".." not in adres


def test_yan_etkili_uc_get_ile_calismaz(sunucu):
    # /api/refresh butceyi harcayan tek uc; GET olarak birakildiginda bir
    # <img src=...> etiketi onu dongude tetikleyebiliyordu.
    assert _durum(sunucu, "/api/refresh") == 405
