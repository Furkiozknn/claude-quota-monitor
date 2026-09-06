"""normalize() ve yardimcilari icin birim testler.

Neden onemli: `/api/oauth/usage` **belgelenmemis** bir uc. Anthropic semayi
haber vermeden degistirebilir. Bu testler gercek bir yanitin kopyasini
fixture olarak tutuyor; sema degisirse veya ayristiriciyi bozarsak burada
yakalanir.

Calistirma:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import (  # noqa: E402
    _as_epoch, _as_percent, _normalize_fallback, extract_meta, normalize,
)

# 6 Eylul 2026'da ucun gercekten dondurdugu yanit (token'a bagli alanlar
# temizlendi). Kod adlari (nimbus_quill, tangelo ...) bilerek birakildi —
# ayristiricinin bunlari elemesi test ediliyor.
GERCEK_YANIT = {
    "five_hour": {"utilization": 48.0, "resets_at": "2026-09-06T22:39:59.843984+00:00",
                  "limit_dollars": None, "used_dollars": None,
                  "remaining_dollars": None, "locked_reason": None},
    "seven_day": {"utilization": 85.0, "resets_at": "2026-09-06T22:59:59.844009+00:00",
                  "limit_dollars": None, "used_dollars": None,
                  "remaining_dollars": None, "locked_reason": None},
    "seven_day_oauth_apps": None,
    "seven_day_opus": None,
    "seven_day_sonnet": None,
    "seven_day_cowork": None,
    "seven_day_omelette": None,
    "tangelo": None,
    "iguana_necktie": None,
    "omelette_promotional": None,
    "nimbus_quill": {"utilization": 0.0, "resets_at": None, "limit_dollars": None,
                     "used_dollars": None, "remaining_dollars": None,
                     "locked_reason": None},
    "cinder_cove": None,
    "copper_kite": None,
    "amber_ladder": None,
    "juniper_tide": None,
    "extra_usage": {"is_enabled": False, "monthly_limit": None, "used_credits": None,
                    "utilization": None, "currency": None, "decimal_places": None,
                    "disabled_reason": None, "user_disabled": True,
                    "spend_limit_reached": False, "credits_ever_enabled": True,
                    "daily": None, "weekly": None},
    "limits": [
        {"kind": "session", "group": "session", "percent": 48, "severity": "normal",
         "resets_at": "2026-09-06T22:39:59.843984+00:00", "scope": None,
         "is_active": False},
        {"kind": "weekly_all", "group": "weekly", "percent": 85, "severity": "warning",
         "resets_at": "2026-09-06T22:59:59.844009+00:00", "scope": None,
         "is_active": False},
        {"kind": "weekly_scoped", "group": "weekly", "percent": 100,
         "severity": "critical", "resets_at": "2026-09-06T22:59:59.844235+00:00",
         "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None},
         "is_active": True},
    ],
    "spend": {"used": {"amount_minor": 0, "currency": "USD", "exponent": 2},
              "limit": None, "percent": 0, "severity": "normal", "enabled": False,
              "disabled_reason": None, "cap": None, "balance": None,
              "auto_reload": None, "disclaimer": "...", "can_purchase_credits": False,
              "can_toggle": False},
    "member_dashboard_available": False,
}


class TestNormalize(unittest.TestCase):
    """limits dizisi birincil kaynak olmali."""

    def setUp(self):
        self.cards = normalize(GERCEK_YANIT)

    def test_limits_dizisinden_uc_kart(self):
        self.assertEqual(len(self.cards), 3)

    def test_kod_adlari_elenir(self):
        # nimbus_quill'in utilization'i var ama kota degil — kart olmamali
        anahtarlar = {c["key"] for c in self.cards}
        for gurultu in ("nimbus_quill", "tangelo", "cinder_cove", "spend"):
            self.assertNotIn(gurultu, anahtarlar)

    def test_severity_uctan_alinir(self):
        by_key = {c["key"]: c for c in self.cards}
        self.assertEqual(by_key["session"]["severity"], "normal")
        self.assertEqual(by_key["weekly_all"]["severity"], "warning")
        self.assertEqual(by_key["weekly_scoped:Fable"]["severity"], "critical")

    def test_aktif_limit_en_ustte(self):
        # Su an daraltan limit ilk sirada olmali
        self.assertTrue(self.cards[0]["is_active"])
        self.assertEqual(self.cards[0]["percent"], 100.0)

    def test_scope_modeli_etikete_girer(self):
        etiket = next(c["label"] for c in self.cards if c["key"] == "weekly_scoped:Fable")
        self.assertIn("Fable", etiket)

    def test_yuzde_olceklenmez(self):
        # limits dizisindeki percent zaten 0-100. 100 -> 100 kalmali.
        yuzdeler = sorted(c["percent"] for c in self.cards)
        self.assertEqual(yuzdeler, [48.0, 85.0, 100.0])

    def test_resets_at_epoch_olur(self):
        for card in self.cards:
            self.assertIsInstance(card["resets_at"], float)


class TestYedekYol(unittest.TestCase):
    """limits dizisi yoksa ust seviye gezinme devreye girmeli."""

    def test_limits_yoksa_yedek_calisir(self):
        yanit = {k: v for k, v in GERCEK_YANIT.items() if k != "limits"}
        cards = normalize(yanit)
        anahtarlar = {c["key"] for c in cards}
        self.assertIn("five_hour", anahtarlar)
        self.assertIn("seven_day", anahtarlar)
        # kod adi yine elenmeli: resets_at'i yok ve bilinen onek degil
        self.assertNotIn("nimbus_quill", anahtarlar)

    def test_duzlestirilmis_sema(self):
        cards = _normalize_fallback({
            "five_hour_utilization": 42,
            "five_hour_resets_at": 1788734399,
        })
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["percent"], 42.0)

    def test_bos_ve_bozuk_girdi_cokmez(self):
        for girdi in (None, {}, [], "metin", 42, {"limits": "dizi degil"}):
            self.assertIsInstance(normalize(girdi), list)


class TestYardimcilar(unittest.TestCase):

    def test_as_percent_oran_modu(self):
        # Yedek yolda sema bilinmedigi icin 0-1 orani kabul edilir
        self.assertEqual(_as_percent(0.85, assume_ratio=True), 85.0)
        # limits dizisinde olcekleme YOK — %1, %100 olmamali
        self.assertEqual(_as_percent(1, assume_ratio=False), 1.0)

    def test_as_percent_sinirlar(self):
        self.assertEqual(_as_percent(150), 100.0)
        self.assertEqual(_as_percent(-5), 0.0)
        self.assertIsNone(_as_percent(None))
        self.assertIsNone(_as_percent(True))      # bool sayi sayilmaz
        self.assertIsNone(_as_percent("metin"))

    def test_as_epoch_bicimleri(self):
        iso = _as_epoch("2026-09-06T22:39:59+00:00")
        self.assertIsInstance(iso, float)
        # milisaniye epoch saniyeye cevrilmeli
        self.assertAlmostEqual(_as_epoch(1788734399000), 1788734399.0, places=0)
        self.assertAlmostEqual(_as_epoch(1788734399), 1788734399.0, places=0)
        self.assertIsNone(_as_epoch(None))
        self.assertIsNone(_as_epoch("tarih degil"))


class TestMeta(unittest.TestCase):

    def test_extra_usage_ve_spend_ayrilir(self):
        meta = extract_meta(GERCEK_YANIT)
        self.assertFalse(meta["extra_usage"]["enabled"])
        self.assertTrue(meta["extra_usage"]["user_disabled"])
        self.assertEqual(meta["spend"]["used"], 0.0)
        self.assertEqual(meta["spend"]["currency"], "USD")

    def test_bozuk_girdi_cokmez(self):
        for girdi in (None, {}, "metin"):
            meta = extract_meta(girdi)
            self.assertIn("extra_usage", meta)
            self.assertIn("spend", meta)


if __name__ == "__main__":
    unittest.main(verbosity=2)
