"""Tutarlilik testleri — gece yapilan hatalarin bir daha olmamasi icin.

Her test, gercekten yasanmis bir hataya karsilik gelir. Hata sinifi:
"birden fazla yerde elle senkron tutulan kopya". Bu testler kopyalarin
birbirinden sapmasini kalici olarak yakalar.

Calistirma:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import palette  # noqa: E402
import server   # noqa: E402

STYLE = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


class TestSurum(unittest.TestCase):
    """Yasanan hata: APP_VERSION 0.1.0'da donmustu, gunluk 0.10.0 diyordu.

    Gunluk (PROGRESS.md) kaldirildi: otonom calisma notuydu, yerel mutlak
    yollar ve artik var olmayan dosyalar iceriyordu. Surum artik tek yerde
    duruyor; karsilastirilacak ikinci kopya kalmadi, karsilastirma testi de
    kalmadi. Geriye surumun bicimini koruyan kontrol kaliyor.
    """

    def test_app_version_bicimi(self):
        self.assertRegex(
            server.APP_VERSION, r"^\d+\.\d+\.\d+$",
            f"server.APP_VERSION={server.APP_VERSION} semver bicimde degil")


class TestPalet(unittest.TestCase):
    """Yasanan hata: koyu tema iki blokta yaziliydi, biri guncellendi digeri
    kaldi; widget paleti panodan sapmisti."""

    def test_css_jetonlari_tek_yerde_tanimli(self):
        # light-dark() ile her jeton bir kez yazilir. Ikinci bir tanim,
        # eski hata sinifinin geri geldigi anlamina gelir.
        for token in palette.CSS_TOKENS:
            adet = len(re.findall(rf"^\s*--{re.escape(token)}\s*:", STYLE, re.M))
            self.assertEqual(
                adet, 1,
                f"--{token} style.css'te {adet} kez tanimli; tam 1 olmali "
                f"(light-dark() ile). Kopya tema blogu geri mi geldi?")

    def test_css_degerleri_palette_ile_ayni(self):
        for token in palette.CSS_TOKENS:
            m = re.search(
                rf"--{re.escape(token)}\s*:\s*light-dark\(\s*(#[0-9a-fA-F]{{6}})\s*,\s*(#[0-9a-fA-F]{{6}})\s*\)",
                STYLE)
            self.assertIsNotNone(m, f"--{token} light-dark(#hex, #hex) bicimde degil")
            self.assertEqual(m.group(1).lower(), palette.LIGHT[token].lower(),
                             f"--{token} acik degeri palette.LIGHT ile uyusmuyor")
            self.assertEqual(m.group(2).lower(), palette.DARK[token].lower(),
                             f"--{token} koyu degeri palette.DARK ile uyusmuyor")

    def test_eski_cift_blok_yok(self):
        # prefers-color-scheme icinde jeton yeniden tanimlanmamali.
        self.assertNotRegex(
            STYLE, r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{[^}]*--bg\s*:",
            "prefers-color-scheme blogu icinde --bg yeniden tanimlanmis; "
            "light-dark() yapisi bozulmus")

    def test_widget_paleti_palette_dan_turetiliyor(self):
        import widget
        for theme in ("light", "dark"):
            self.assertEqual(widget.PALETTE[theme], palette.widget_palette(theme))


class TestVarliklar(unittest.TestCase):
    """Yasanan hata: favicon 404 veriyordu, konsola bakana kadar kimse gormedi."""

    def test_html_yerel_varliklari_mevcut(self):
        refs = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', INDEX)
        self.assertTrue(refs, "index.html'de hic src/href bulunamadi")
        for ref in refs:
            if ref.startswith(("data:", "http:", "https:", "#", "mailto:")):
                continue
            yol = ROOT / "web" / ref.lstrip("/")
            self.assertTrue(yol.is_file(), f"index.html {ref} dosyasina isaret ediyor ama yok")

    def test_favicon_var(self):
        self.assertIn('rel="icon"', INDEX, "favicon yok — konsolda 404 verir")


class TestTurkce(unittest.TestCase):
    """Yasanan hata: kullaniciya gorunen etiketler ASCII yazilmisti
    ('Haftalik — Tum modeller'). Kod yorumu ASCII kalabilir; kullanicinin
    gordugu metin kalamaz."""

    ASCII_TUZAKLAR = ("Haftalik", "Tum ", "Kapsamli", "Aylik", "KRITIK", "sifir")

    def test_kind_labels_turkce(self):
        for v in server.KIND_LABELS.values():
            for tuzak in self.ASCII_TUZAKLAR:
                self.assertNotIn(tuzak, v, f"KIND_LABELS icinde ASCII Turkce: {v!r}")

    def test_window_labels_turkce(self):
        for v in server.WINDOW_LABELS.values():
            for tuzak in self.ASCII_TUZAKLAR:
                self.assertNotIn(tuzak, v, f"WINDOW_LABELS icinde ASCII Turkce: {v!r}")

    def test_sev_word_turkce(self):
        self.assertEqual(server.SEV_WORD["critical"], "KRİTİK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
