"""one_shot() (--once/--compact) icin kenar durum testleri.

Neden onemli: bu, yeni bir kullanicinin ilk calistirdigi kod yolu. Cokme
yerine anlasilir bir mesaj ve dogru cikis kodu vermeli.

Calistirma:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


class TestOneShotKenarDurumlar(unittest.TestCase):
    def _run(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = server.one_shot(port=8110, compact=False)
        return code, out.getvalue(), err.getvalue()

    def test_ag_yok_cokmez(self):
        """Ag hatasinda fetch_usage status=0 doner; cokme yok, anlasilir mesaj."""
        with patch.object(server, "_from_local_server", return_value=None), \
             patch.object(server, "read_token", return_value=("tok", {})), \
             patch.object(server, "fetch_usage", return_value=(0, {"_error": "boom"})):
            code, _, err = self._run()
        self.assertEqual(code, 3)
        self.assertIn("Ağa ulaşılamadı", err)

    def test_yetki_hatasi_401_anlasilir_mesaj(self):
        with patch.object(server, "_from_local_server", return_value=None), \
             patch.object(server, "read_token", return_value=("tok", {})), \
             patch.object(server, "fetch_usage", return_value=(401, {"_error": "unauthorized"})):
            code, _, err = self._run()
        self.assertEqual(code, 3)
        self.assertIn("401", err)
        self.assertIn("Claude Code", err)

    def test_bozuk_yanit_kota_bulunamadi(self):
        """Uc 200 doner ama govde taninabilir bir kota alani tasimiyor."""
        with patch.object(server, "_from_local_server", return_value=None), \
             patch.object(server, "read_token", return_value=("tok", {})), \
             patch.object(server, "fetch_usage", return_value=(200, {"_unparsed": "<html>bozuk</html>"})):
            code, _, err = self._run()
        self.assertEqual(code, 4)
        self.assertIn("bulunamadı", err)

    def test_token_yok_anlasilir_mesaj(self):
        with patch.object(server, "_from_local_server", return_value=None), \
             patch.object(server, "read_token",
                          return_value=(None, {"error": "Kimlik dosyasi bulunamadi."})):
            code, _, err = self._run()
        self.assertEqual(code, 2)
        self.assertIn("Kimlik dosyasi", err)

    def test_basarili_yol_hala_calisiyor(self):
        """Kenar durum duzeltmeleri normal basarili yolu bozmamali."""
        raw = {"limits": [{"kind": "session", "percent": 42.0, "is_active": True}]}
        with patch.object(server, "_from_local_server", return_value=None), \
             patch.object(server, "read_token", return_value=("tok", {"subscription": "max"})), \
             patch.object(server, "fetch_usage", return_value=(200, raw)):
            code, out, _ = self._run()
        self.assertEqual(code, 0)
        self.assertIn("42%", out)


if __name__ == "__main__":
    unittest.main()
