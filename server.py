"""claude-quota-monitor — Claude kota panosu.

Anthropic'in /api/oauth/usage ucundan 5 saatlik ve haftalik kota
kullanimini cekip yerel bir web panosunda gosterir.

Tasarim ilkeleri
----------------
* **Nazik olmak.** Varsayilan 180 sn'de bir sorgu. 429/5xx gelirse ustel
  backoff (max 900 sn). Token ROTASYONU YOK — limite carparsak bekleriz,
  son bilinen degeri gostermeye devam ederiz. Anthropic'in koydugu
  korumayi asmaya calismayiz.
* **Yerel kalmak.** Sunucu yalnizca 127.0.0.1'e baglanir. Disari giden tek
  istek api.anthropic.com'adir. Telemetri yok.
* **Sadece okumak.** .credentials.json okunur, asla yazilmaz. Token yenileme
  denenmez; suresi dolmussa kullaniciya "Claude Code'u calistir" denir.
* **Sekle bagimli olmamak.** Ucun cevap semasi belgelenmemis ve degisebilir.
  normalize() ne gelirse gelir kart uretmeye calisir, ham JSON /api/raw'da
  her zaman durur.

Bagimlilik yok — yalnizca Python 3.8+ standart kutuphanesi.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_NAME = "claude-quota-monitor"
APP_VERSION = "0.10.0"

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
DEFAULT_DB = Path.home() / ".claude" / "quota-monitor.db"
WEB_DIR = Path(__file__).resolve().parent / "web"

# Nazik sorgu politikasi
POLL_INTERVAL = 180          # normal aralik (sn)
BACKOFF_START = 60           # ilk hata sonrasi bekleme
BACKOFF_MAX = 900            # ust sinir — bunun otesine cikmayiz
REQUEST_TIMEOUT = 20

# Kart uretiminde aranan anahtar kaliplari (uc semasi belgelenmemis)
PCT_KEYS = re.compile(r"utilization|percent|pct|used_percent|usage", re.I)
RESET_KEYS = re.compile(r"reset|resets_at|expires|refresh|renew", re.I)

# Ucun "limits" dizisindeki kind degerlerine okunakli etiket.
# Bu dizi birincil kaynak: yapisi duzgun ve severity'yi ucun kendisi veriyor.
KIND_LABELS = {
    "session": "5 Saatlik Oturum",
    "weekly_all": "Haftalık — Tüm modeller",
    "weekly_scoped": "Haftalık — Kapsamlı",
    "monthly": "Aylık",
    "opus": "Opus",
    "sonnet": "Sonnet",
}

# Yedek yol icin ust seviye anahtar etiketleri
WINDOW_LABELS = {
    "five_hour": "5 Saatlik Oturum",
    "seven_day": "Haftalık (7 gün)",
    "seven_day_opus": "Haftalık — Opus",
    "seven_day_sonnet": "Haftalık — Sonnet",
    "seven_day_cowork": "Haftalık — Cowork",
    "seven_day_oauth_apps": "Haftalık — OAuth uygulamaları",
    "monthly": "Aylık",
}

# Ucun cevabinda yayinlanmamis ozelliklere ait kod adlari donuyor
# (nimbus_quill, tangelo, iguana_necktie, cinder_cove ...). Cogu null;
# null olmayanlari da kota sanip kart uretmeyelim.
NOISE_KEYS = {
    "spend", "extra_usage", "limits", "member_dashboard_available",
}
KNOWN_WINDOW_PREFIXES = ("five_hour", "seven_day", "monthly", "daily")


# --------------------------------------------------------------------------
# Kimlik
# --------------------------------------------------------------------------

def read_token() -> tuple[str | None, dict]:
    """Mevcut OAuth token'ini okur. Asla yazmaz, asla yenilemez.

    Doner: (token_or_None, meta). meta her zaman doldurulur ki arayuz
    sorunu aciklayabilsin.
    """
    meta: dict = {"source": str(CREDENTIALS), "expired": None, "expires_at": None}

    if not CREDENTIALS.exists():
        meta["error"] = "Kimlik dosyasi bulunamadi. Claude Code'a giris yaptin mi?"
        return None, meta

    try:
        with CREDENTIALS.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # bozuk/kilitli dosya
        meta["error"] = f"Kimlik dosyasi okunamadi: {type(exc).__name__}"
        return None, meta

    oauth = data.get("claudeAiOauth") or data.get("oauth") or {}
    token = oauth.get("accessToken") or oauth.get("access_token")
    meta["subscription"] = oauth.get("subscriptionType") or oauth.get("subscription_type")

    expires_at = oauth.get("expiresAt") or oauth.get("expires_at")
    if expires_at:
        # ms veya sn epoch olabilir
        ts = float(expires_at)
        if ts > 1e12:
            ts /= 1000.0
        meta["expires_at"] = ts
        meta["expired"] = ts < time.time()

    if not token:
        meta["error"] = "Kimlik dosyasinda accessToken yok."
        return None, meta

    if meta["expired"]:
        meta["error"] = (
            "Token'in suresi dolmus. Claude Code'da bir komut calistir; "
            "kendisi yeniler, bu pano da otomatik toparlar."
        )
        # Yine de deneriz — saat kaymasi olabilir; 401 gelirse zaten anlariz.

    return token, meta


# --------------------------------------------------------------------------
# Uzak sorgu
# --------------------------------------------------------------------------

def fetch_usage(token: str) -> tuple[int, object]:
    """Uca TEK istek atar. Yeniden deneme yok — onu poller yonetir."""
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
            "User-Agent": f"{APP_NAME}/{APP_VERSION} (local; polite; no-rotation)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, {"_unparsed": body[:4000]}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        try:
            detail = json.loads(detail)
        except Exception:
            pass
        return exc.code, {"_error": detail}
    except Exception as exc:
        return 0, {"_error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------
# Sekilden bagimsiz ayristirma
# --------------------------------------------------------------------------

def _as_epoch(value) -> float | None:
    """Epoch (sn/ms) veya ISO-8601 -> epoch saniye."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value / 1000.0 if value > 1e12 else float(value)
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return _as_epoch(int(raw))
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _as_percent(value, assume_ratio: bool = False) -> float | None:
    """Yuzde degerini normalize eder.

    `limits` dizisindeki percent alanlari zaten 0-100 — orada assume_ratio
    kapalidir, yoksa %1 gelen deger %100 gorunurdu. Yedek yolda semayi
    bilmedigimiz icin 0-1 araligini oran kabul ederiz.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        pct = float(value)
        if assume_ratio and 0.0 < pct <= 1.0:
            pct *= 100.0
        return max(0.0, min(100.0, pct))
    return None


def normalize(raw) -> list[dict]:
    """Ham cevabi kart listesine cevirir.

    Birincil kaynak raw["limits"] dizisi: kind / group / percent / severity /
    resets_at / scope / is_active alanlariyla zaten duzgun yapili. Ayrica
    severity'yi ucun kendisi soyluyor — biz esik uydurmuyoruz.

    Uc belgelenmemis; sema degisirse _normalize_fallback() devreye girer.
    """
    if not isinstance(raw, dict):
        return []

    limits = raw.get("limits")
    if isinstance(limits, list) and limits:
        cards: list[dict] = []
        for item in limits:
            if not isinstance(item, dict):
                continue
            pct = _as_percent(item.get("percent"))
            if pct is None:
                continue

            kind = str(item.get("kind") or "?")
            label = KIND_LABELS.get(kind, kind.replace("_", " ").title())
            key = kind

            # weekly_scoped gibi girdilerde hangi modele ait oldugu scope'ta
            scope = item.get("scope")
            model = None
            if isinstance(scope, dict):
                m = scope.get("model")
                if isinstance(m, dict):
                    model = m.get("display_name") or m.get("id")
            if model:
                label = f"{label} · {model}"
                key = f"{kind}:{model}"

            cards.append({
                "key": key,
                "label": label,
                "percent": pct,
                "resets_at": _as_epoch(item.get("resets_at")),
                "severity": item.get("severity"),
                "is_active": bool(item.get("is_active")),
                "group": item.get("group"),
                "extra": {},
            })

        if cards:
            # Su an daraltan limit en ustte; sonra doluluga gore azalan.
            cards.sort(key=lambda c: (not c["is_active"], -(c["percent"] or 0)))
            return cards

    return _normalize_fallback(raw)


def _normalize_fallback(raw: dict) -> list[dict]:
    """limits dizisi yoksa ust seviye sozlukleri gezerek kart uretir.

    Uc, yayinlanmamis ozelliklere ait kod adlari da donduruyor
    (nimbus_quill, tangelo, cinder_cove ...). Bunlari kota sanmamak icin
    yalnizca bilinen pencere onekleri veya sifirlanma zamani olanlar alinir.
    """
    cards: list[dict] = []

    def harvest(key: str, obj) -> dict | None:
        if not isinstance(obj, dict) or key in NOISE_KEYS or key.startswith("_"):
            return None
        pct = reset = None
        for field, value in obj.items():
            if pct is None and PCT_KEYS.search(field):
                pct = _as_percent(value, assume_ratio=True)
            if reset is None and RESET_KEYS.search(field):
                reset = _as_epoch(value)
        if pct is None and reset is None:
            return None
        # Kod adi gurultusunu ele: ya taninan bir pencere onegi olsun,
        # ya da gercek bir sifirlanma zamani tasisin.
        if not key.startswith(KNOWN_WINDOW_PREFIXES) and reset is None:
            return None
        return {
            "key": key,
            "label": WINDOW_LABELS.get(key, key.replace("_", " ").title()),
            "percent": pct,
            "resets_at": reset,
            "severity": None,
            "is_active": False,
            "group": None,
            "extra": {k: v for k, v in obj.items() if isinstance(v, (str, int, float, bool))},
        }

    for key, value in raw.items():
        if key.startswith("_"):
            continue
        card = harvest(key, value)
        if card:
            cards.append(card)
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                sub = harvest(sub_key, sub_value)
                if sub:
                    cards.append(sub)

    # Duzlestirilmis sema: {"five_hour_utilization": 23, ...}
    if not cards:
        flat: dict[str, dict] = {}
        for key, value in raw.items():
            match = re.match(r"(.+?)_(utilization|percent|pct|resets_at|reset)$", key, re.I)
            if not match:
                continue
            base, kind = match.group(1), match.group(2).lower()
            slot = flat.setdefault(base, {})
            if kind in ("utilization", "percent", "pct"):
                slot["percent"] = _as_percent(value, assume_ratio=True)
            else:
                slot["resets_at"] = _as_epoch(value)
        for base, slot in flat.items():
            cards.append({
                "key": base,
                "label": WINDOW_LABELS.get(base, base.replace("_", " ").title()),
                "percent": slot.get("percent"),
                "resets_at": slot.get("resets_at"),
                "severity": None,
                "is_active": False,
                "group": None,
                "extra": {},
            })

    order = list(WINDOW_LABELS)
    cards.sort(key=lambda c: (order.index(c["key"]) if c["key"] in order else 99, c["key"]))
    return cards


def extract_meta(raw) -> dict:
    """Kota kartina girmeyen ama isine yarayan yan bilgiler.

    extra_usage = plan limitini astiginda devreye giren ek kredi;
    spend = o krediden harcanan tutar. Ikisi de kota penceresi degil,
    o yuzden kart yapilmaz.
    """
    meta: dict = {"extra_usage": None, "spend": None}
    if not isinstance(raw, dict):
        return meta

    extra = raw.get("extra_usage")
    if isinstance(extra, dict):
        meta["extra_usage"] = {
            "enabled": bool(extra.get("is_enabled")),
            "user_disabled": bool(extra.get("user_disabled")),
            "utilization": _as_percent(extra.get("utilization")),
            "monthly_limit": extra.get("monthly_limit"),
            "used_credits": extra.get("used_credits"),
        }

    spend = raw.get("spend")
    if isinstance(spend, dict):
        used = spend.get("used") if isinstance(spend.get("used"), dict) else {}
        amount = None
        minor = used.get("amount_minor")
        if isinstance(minor, (int, float)):
            amount = minor / (10 ** int(used.get("exponent") or 2))
        meta["spend"] = {
            "enabled": bool(spend.get("enabled")),
            "used": amount,
            "currency": used.get("currency"),
            "percent": _as_percent(spend.get("percent")),
        }

    return meta


# --------------------------------------------------------------------------
# Depolama
# --------------------------------------------------------------------------

def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS samples (
               ts REAL NOT NULL,
               window_key TEXT NOT NULL,
               percent REAL,
               resets_at REAL,
               PRIMARY KEY (ts, window_key)
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_key_ts ON samples(window_key, ts)")
    conn.commit()
    return conn


def store(conn: sqlite3.Connection, cards: list[dict]) -> None:
    now = time.time()
    rows = [(now, c["key"], c["percent"], c["resets_at"]) for c in cards if c["percent"] is not None]
    if not rows:
        return
    conn.executemany("INSERT OR REPLACE INTO samples VALUES (?,?,?,?)", rows)
    conn.commit()


def burn_rate(conn: sqlite3.Connection, window_key: str,
              lookback: int = 3600) -> dict | None:
    """Son bir saatteki tuketim hizindan limite varis zamanini tahmin eder.

    Pencere sifirlandiginda yuzde dusuyor; o yuzden yalnizca *son
    sifirlanmadan bu yana* olan yukselisi olcuyoruz. Yoksa sifirlanmayi
    "negatif tuketim" sanip sacma tahmin uretirdik.
    """
    rows = conn.execute(
        "SELECT ts, percent FROM samples WHERE window_key=? AND ts>=? ORDER BY ts",
        (window_key, time.time() - lookback),
    ).fetchall()

    run: list[tuple[float, float]] = []
    for ts, pct in rows:
        if pct is None:
            continue
        if run and pct < run[-1][1] - 1.0:   # belirgin dusus => pencere sifirlandi
            run = []
        run.append((ts, pct))

    if len(run) < 2:
        return None

    span = run[-1][0] - run[0][0]
    delta = run[-1][1] - run[0][1]
    if span < 300 or delta <= 0:             # cok kisa orneklem veya artis yok
        return None

    per_hour = delta / (span / 3600.0)
    remaining = max(0.0, 100.0 - run[-1][1])
    eta = time.time() + (remaining / per_hour) * 3600.0 if per_hour > 0 else None

    return {
        "percent_per_hour": round(per_hour, 2),
        "eta": eta,
        "samples": len(run),
        "span_sec": round(span),
    }


def history(conn: sqlite3.Connection, hours: int = 24) -> dict[str, list]:
    since = time.time() - hours * 3600
    rows = conn.execute(
        "SELECT window_key, ts, percent FROM samples WHERE ts >= ? ORDER BY ts", (since,)
    ).fetchall()
    out: dict[str, list] = {}
    for key, ts, pct in rows:
        out.setdefault(key, []).append([ts, pct])
    return out


# --------------------------------------------------------------------------
# Poller
# --------------------------------------------------------------------------

class Poller(threading.Thread):
    """Arka planda nazikce sorgular. Token rotasyonu yapmaz."""

    daemon = True

    def __init__(self, conn: sqlite3.Connection, interval: int = POLL_INTERVAL,
                 notify_at: int = 0):
        super().__init__(name="poller")
        self.conn = conn
        self.interval = interval
        self.notify_at = notify_at
        # Hangi pencere icin esik bildirimi zaten atildi. Pencere sifirlaninca
        # temizlenir ki bir sonraki dolusta yeniden haber verilsin.
        self._notified: dict[str, bool] = {}
        # Ilk basarili sorguda bildirim ATILMAZ, yalnizca mevcut durum
        # kaydedilir. Yoksa program her acildiginda zaten dolu olan pencereler
        # icin bildirim yagardi — gece yarisi hos olmaz.
        self._seeded = False
        self.backoff = 0
        self.lock = threading.Lock()
        self.state: dict = {
            "cards": [],
            "meta": None,
            "raw": None,
            "http_status": None,
            "last_ok": None,
            "last_try": None,
            "next_try": None,
            "error": None,
            "note": None,
            "consecutive_errors": 0,
        }
        self._wake = threading.Event()

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.state, default=str))

    def poke(self) -> None:
        """Elle yenileme — yine de nazik aralik korunur."""
        self._wake.set()

    def run(self) -> None:
        while True:
            self._tick()
            wait = self.backoff or self.interval
            with self.lock:
                self.state["next_try"] = time.time() + wait
            self._wake.wait(timeout=wait)
            self._wake.clear()

    def _check_thresholds(self, cards: list[dict]) -> None:
        """Esik asildiginda bir kez bildirim gonderir.

        Kurallar:
        * Ilk basarili sorguda hicbir sey gonderilmez (bkz. _seeded).
        * Pencere basina tek bildirim; pencere sifirlanip yuzde belirgin
          sekilde dusunce yeniden hak kazanir.
        * Gonderim ayri bir is parcaciginda — PowerShell birkac saniye
          surebiliyor, poller onu beklemesin.
        """
        if not self.notify_at:
            return

        for card in cards:
            key, pct = card.get("key"), card.get("percent")
            if not key or pct is None:
                continue

            crossed = pct >= self.notify_at
            already = self._notified.get(key, False)

            if crossed and not already:
                self._notified[key] = True
                if self._seeded:
                    threading.Thread(
                        target=self._send_notice, args=(card,), daemon=True
                    ).start()
            elif already and pct < self.notify_at - 5:
                # Belirgin dusus = pencere sifirlandi. 5 puanlik pay,
                # esigin tam ustunde salinan degerlerin bildirim yagmuru
                # yaratmasini onler.
                self._notified[key] = False

        self._seeded = True

    def _send_notice(self, card: dict) -> None:
        try:
            from notify import notify as send
        except Exception:
            return
        left = ""
        if card.get("resets_at"):
            secs = int(card["resets_at"] - time.time())
            if secs > 0:
                h, m = secs // 3600, (secs % 3600) // 60
                left = f" Sıfırlanmasına {h} sa {m} dk."
        try:
            send(f"Claude kota: {card['label']}",
                 f"%{card['percent']:.0f} doldu.{left}")
        except Exception:
            pass

    def _tick(self) -> None:
        token, meta = read_token()
        now = time.time()

        if not token:
            with self.lock:
                self.state.update(
                    last_try=now,
                    error=meta.get("error", "Token yok"),
                    note="Kimlik dosyasi hazir olunca otomatik devam eder.",
                )
            self.backoff = min(max(self.backoff * 2, BACKOFF_START), BACKOFF_MAX)
            return

        status, body = fetch_usage(token)
        with self.lock:
            self.state["last_try"] = now
            self.state["http_status"] = status
            self.state["subscription"] = meta.get("subscription")

        if status == 200:
            cards = normalize(body)
            store(self.conn, cards)
            self._check_thresholds(cards)
            self.backoff = 0
            with self.lock:
                self.state.update(
                    cards=cards,
                    meta=extract_meta(body),
                    raw=body,
                    last_ok=now,
                    error=None,
                    consecutive_errors=0,
                    note=None if cards else
                    "Cevap alindi ama tanidik bir kota alani bulunamadi — Ham veri sekmesine bak.",
                )
            return

        # --- hata yolu: BEKLE, token yenileme/rotasyon YOK ---
        if status == 429:
            note = ("Uc gecici olarak sorgu limitine takildi. Bekleniyor — "
                    "son bilinen degerler gosteriliyor. (Token rotasyonu yapilmaz.)")
        elif status == 401:
            note = ("Token reddedildi (401). Claude Code'da bir komut calistir; "
                    "token yenilenince pano toparlar.")
        elif status == 0:
            note = "Aga ulasilamadi."
        else:
            note = f"Beklenmeyen HTTP {status}."

        self.backoff = min(max(self.backoff * 2, BACKOFF_START), BACKOFF_MAX)
        with self.lock:
            self.state["consecutive_errors"] += 1
            self.state.update(error=str(body.get("_error", body))[:500], note=note, raw=body)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

SESSION_WINDOW = 5 * 3600     # 5 saatlik oturum penceresi


def _attribution_payload(poller: "Poller") -> dict:
    """Mevcut 5 saatlik pencereyi yerel transcript'lerle iliskilendirir.

    Pencerenin baslangicini ucun verdigi resets_at'ten geri sayarak buluruz;
    boylece atif tam olarak *o pencereyi dolduran* araligi kapsar.
    """
    snap = poller.snapshot()
    session_card = next(
        (c for c in (snap.get("cards") or []) if c.get("key") == "session"), None)

    if session_card and session_card.get("resets_at"):
        since = float(session_card["resets_at"]) - SESSION_WINDOW
        kaynak = "uçtan gelen sıfırlanma zamanı"
    else:
        since = time.time() - SESSION_WINDOW
        kaynak = "tahmini (uç sıfırlanma zamanı vermedi)"

    try:
        import attribution
        data = attribution.scan(since)
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}

    data["window_source"] = kaynak
    data["session_percent"] = session_card.get("percent") if session_card else None

    # Pencere yuzdesini paylara dagit: "%60 doldu, bunun %48'i su projeden".
    # Bu bir ORAN TAHMINI — Anthropic yuzdenin hangi tokenlardan geldigini
    # soylemiyor, biz yerel token agirliklarina gore bolusuyoruz.
    pct = data["session_percent"]
    if isinstance(pct, (int, float)) and data["totals"]["tokens"]:
        for item in data["projects"]:
            item["window_percent"] = round(pct * item["share"] / 100.0, 1)
        for item in data["models"]:
            item["window_percent"] = round(pct * item["share"] / 100.0, 1)

    return data


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


def make_handler(poller: Poller, conn: sqlite3.Connection):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"{APP_NAME}/{APP_VERSION}"

        def log_message(self, fmt, *args):  # gurultuyu kes
            pass

        def _send(self, code: int, payload: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]

            if path == "/api/status":
                snap = poller.snapshot()
                for card in snap.get("cards") or []:
                    burn = burn_rate(conn, card.get("key", ""))
                    card["burn"] = burn
                    # Asil soru: pencere sifirlanmadan once limite carpar miyim?
                    if burn and burn.get("eta") and card.get("resets_at"):
                        card["will_exhaust"] = burn["eta"] < card["resets_at"]
                    else:
                        card["will_exhaust"] = None
                snap["server_time"] = time.time()
                snap["poll_interval"] = poller.interval
                snap["version"] = APP_VERSION
                self._json(snap)
                return

            if path == "/api/history":
                self._json(history(conn))
                return

            if path == "/api/attribution":
                self._json(_attribution_payload(poller))
                return

            if path == "/api/raw":
                self._json(poller.snapshot().get("raw"))
                return

            if path == "/api/refresh":
                poller.poke()
                self._json({"ok": True})
                return

            # statik dosyalar
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (WEB_DIR / rel).resolve()
            if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            ctype = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
            self._send(200, target.read_bytes(), ctype)

    return Handler


# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Tek seferlik terminal ciktisi
# --------------------------------------------------------------------------

SHORT = {
    "session": "5s", "weekly_all": "7g", "weekly_scoped": "kaps",
    "five_hour": "5s", "seven_day": "7g",
}
SEV_MARK = {"critical": "!", "warning": "*", "normal": ""}
SEV_WORD = {"critical": "KRİTİK", "warning": "dikkat", "normal": "normal"}


def _short_name(card: dict) -> str:
    key = str(card.get("key", ""))
    if ":" in key:                      # weekly_scoped:Fable -> model adi
        return key.split(":", 1)[1]
    return SHORT.get(key, key[:6])


def _from_local_server(port: int) -> dict | None:
    """Calisan sunucu varsa ondan oku — boylece uca EK sorgu gitmez."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/status", timeout=3
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data if data.get("last_ok") else None
    except Exception:
        return None


def _bar(pct: float, width: int = 10) -> str:
    filled = int(round(min(100.0, max(0.0, pct)) / 100.0 * width))
    return "#" * filled + "." * (width - filled)


def _fmt_left(epoch: float | None) -> str:
    if not epoch:
        return "-"
    secs = int(epoch - time.time())
    if secs <= 0:
        return "şimdi"
    h, m = secs // 3600, (secs % 3600) // 60
    if h >= 24:
        return f"{h // 24}g{h % 24}s"
    return f"{h}s{m:02d}dk" if h else f"{m}dk"


def one_shot(port: int, compact: bool) -> int:
    """Tarayici acmadan durumu yazdirir ve cikar.

    Once calisan sunucuya bakar (ek sorgu yok). Yoksa tek bir dogrudan
    sorgu yapar — yine rotasyon yok, tekrar denemesi yok.
    """
    data = _from_local_server(port)
    source = "yerel sunucu"

    if data is None:
        token, meta = read_token()
        if not token:
            print(meta.get("error", "Token okunamadı"), file=sys.stderr)
            return 2
        status, body = fetch_usage(token)
        if status != 200:
            print(f"Uç HTTP {status} döndü.", file=sys.stderr)
            return 3
        data = {"cards": normalize(body), "subscription": meta.get("subscription")}
        source = "doğrudan uç"

    cards = [c for c in (data.get("cards") or []) if c.get("percent") is not None]
    if not cards:
        print("Kota bilgisi bulunamadı.", file=sys.stderr)
        return 4

    if compact:
        parts = []
        for card in cards:
            sev = str(card.get("severity") or "").lower()
            parts.append(f"{_short_name(card)} {card['percent']:.0f}%{SEV_MARK.get(sev, '')}")
        print(" | ".join(parts))
        return 0

    plan = data.get("subscription") or "?"
    print(f"Claude kota — {plan}")
    for card in cards:
        sev = str(card.get("severity") or "").lower()
        mark = " <" if card.get("is_active") else "  "
        print(f"  {card['label'][:30]:<30} [{_bar(card['percent'])}] "
              f"{card['percent']:>3.0f}%  {SEV_WORD.get(sev, sev or '-'):<7}"
              f" sıfır: {_fmt_left(card.get('resets_at')):<8}{mark}")
    print(f"  kaynak: {source}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude kota panosu (yerel)")
    parser.add_argument("--once", action="store_true",
                        help="Sunucu baslatma; durumu yazdir ve cik")
    parser.add_argument("--compact", action="store_true",
                        help="Tek satir cikti (statusline icin). --once ima eder")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8110")))
    parser.add_argument("--host", default="127.0.0.1",
                        help="Varsayilan 127.0.0.1. Degistirmeni onermem.")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL,
                        help=f"Sorgu araligi (sn). Varsayilan {POLL_INTERVAL}. "
                             "Daha kisasi ucun limitine carpar.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--notify-at", type=int, default=90, metavar="YUZDE",
                        help="Bu yuzde asilinca Windows bildirimi gonder. "
                             "0 = kapali. Varsayilan 90.")
    args = parser.parse_args()

    # Tek seferlik mod: sunucu baslatmaz, veritabani acmaz, hemen cikar.
    if args.once or args.compact:
        return one_shot(args.port, args.compact)

    if args.interval < 60:
        print("[!] Aralik 60 sn'nin altina indirilemez (nazik olma politikasi). 60 kullaniliyor.")
        args.interval = 60

    if args.host != "127.0.0.1":
        print(f"[!] DIKKAT: {args.host} adresine baglaniyorsun. Panoda kota "
              "bilgin var; ag uzerinden erisilebilir hale gelir.")

    conn = init_db(args.db)
    poller = Poller(conn, interval=args.interval, notify_at=args.notify_at)
    poller.start()

    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(poller, conn))
    url = f"http://{args.host}:{args.port}/"

    print(f"{APP_NAME} {APP_VERSION}")
    print(f"  Pano      : {url}")
    print(f"  Sorgu     : {args.interval} sn'de bir (backoff max {BACKOFF_MAX} sn)")
    print(f"  Bildirim  : " + (f"%{args.notify_at} ustunde" if args.notify_at else "kapali"))
    print(f"  Geçmiş    : {args.db}")
    print(f"  Kimlik    : {CREDENTIALS} (yalnızca okunur)")
    print("  Token rotasyonu YAPILMAZ. Ctrl+C ile durdurulur.")

    if not args.no_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatiliyor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
