"""claude-quota-monitor — masaustu widget'i.

Ekranin kosesinde duran, cerceve siz, her zaman ustte kucuk bir pencere.
5 saatlik ve haftalik kota doluluklarini surekli gosterir.

Mimari karar
------------
Bu widget **Anthropic'e hic istek atmaz.** Yerel server.py'nin
/api/status ucundan okur. Boylece:

* Uc noktaya giden sorgu sayisi degismez — nazik olma politikasi korunur.
* Pano ve widget her zaman ayni veriyi gosterir.
* Widget'i kapatip acmak sorgu israfina yol acmaz.

Sunucu kapaliysa widget onu kendisi baslatabilir (--autostart).

Bagimlilik yok — tkinter Python standart kutuphanesinde.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# tkinter modul duzeyinde ice aktarilmiyor: bu dosya yalnizca PALETTE'i okumak
# icin de import ediliyor (tests/test_consistency.py) ve basliksiz makinede
# tkinter yok -- modul duzeyindeki import butun test kosusunu dusuruyordu.
# Yukleme GUI acilirken, Widget kurulurken yapilir.
tk = None


def _tkinter_yukle():
    """tkinter'i ice aktarip modul genelinde kullanilabilir kilar."""
    global tk
    if tk is None:
        try:
            import tkinter
        except ImportError as exc:      # pragma: no cover - ekransiz makine
            raise SystemExit(
                "tkinter bulunamadi; widget grafik arayuz gerektiriyor. "
                "Linux'ta: paket yoneticisinden python3-tk kur. "
                "Arayuz istemiyorsan panoyu kullan: python server.py"
            ) from exc
        tk = tkinter
    return tk

APP_DIR = Path(__file__).resolve().parent
SETTINGS = Path.home() / ".claude" / "quota-widget.json"

REFRESH_MS = 15_000          # yerel sunucuya bakma sikligi (Anthropic'e degil)
RETRY_MS = 5_000             # sunucu kapaliyken tekrar deneme

SNAP_PX = 24                 # bu mesafeye yaklasinca kenara yapisir
WIDGET_W = 190

# Gosterim modlari. "mini" yalnizca su an seni fiilen sinirlayan limiti
# gosterir — ekranda en az yer kaplayan hali.
MODES = ("full", "compact", "mini")
MODE_ROWS = {"full": 3, "compact": 2, "mini": 1}
MODE_LABELS = {"full": "Tam (3 satır)", "compact": "Kompakt (2 satır)",
               "mini": "Mini (1 satır)"}

# Kompakt etiketler — dar alanda uzun isim sigmiyor
SHORT_LABELS = {
    "session": "5s",
    "weekly_all": "7g",
    "weekly_scoped": "kaps",
    "five_hour": "5s",
    "seven_day": "7g",
}

# Renkler tek kaynaktan gelir: palette.py. Burada ikinci bir kopya tutmak
# panodan sapmaya yol aciyordu (v0.9.0'da yakalandi). Widget'ta rozet
# metni yok, o yuzden *-ink ailesine ihtiyac duymuyor.
try:
    from palette import widget_palette as _widget_palette
    PALETTE = {"dark": _widget_palette("dark"), "light": _widget_palette("light")}
except Exception:  # widget tek basina kopyalanmissa yine de calissin
    PALETTE = {
        "dark": {"bg": "#1c1f25", "fg": "#e6e8ec", "muted": "#9aa3b0",
                 "track": "#2b3038", "border": "#2d323b",
                 "ok": "#3fb56b", "warn": "#e09a3a", "danger": "#e05e5e"},
        "light": {"bg": "#ffffff", "fg": "#1b1e23", "muted": "#666e7a",
                  "track": "#e6e9ee", "border": "#e2e5ea",
                  "ok": "#197f45", "warn": "#a85f08", "danger": "#c62f2f"},
    }


def load_settings() -> dict:
    try:
        with SETTINGS.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        with SETTINGS.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass  # konum kaydedilemezse widget yine calisir


class Widget:
    def __init__(self, port: int, theme: str, autostart: bool, mode: str):
        self.port = port
        self.autostart = autostart
        self.mode = mode if mode in MODES else "full"
        self.settings = load_settings()
        self.colors = PALETTE[theme if theme in PALETTE else "dark"]
        self.theme_name = theme
        self.server_proc: subprocess.Popen | None = None
        self.cards: list[dict] = []
        self.offline = True

        _tkinter_yukle()
        self.root = tk.Tk()
        self.root.title("Claude Kota")
        self.root.overrideredirect(True)              # cerceve yok
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", float(self.settings.get("alpha", 0.94)))
        except Exception:
            pass

        self.root.update_idletasks()
        x = self.settings.get("x")
        y = self.settings.get("y")
        if x is None or y is None:
            x = self.root.winfo_screenwidth() - WIDGET_W - 20   # sag ust kose
            y = 40
        # Kayitli konum ekran disinda kalmis olabilir (monitor degistiyse,
        # cozunurluk dustuyse). Gorunur alana geri cekiyoruz.
        self._place(int(x), int(y))

        self.canvas = tk.Canvas(
            self.root, width=WIDGET_W, height=64, highlightthickness=1,
            highlightbackground=self.colors["border"], bg=self.colors["bg"],
        )
        self.canvas.pack()

        self._bind_events()
        self._build_menu()
        self.tick()

    # ---------------- olaylar ----------------

    def _bind_events(self) -> None:
        c = self.canvas
        c.bind("<Button-1>", self._drag_start)
        c.bind("<B1-Motion>", self._drag_move)
        c.bind("<ButtonRelease-1>", self._drag_end)
        c.bind("<Double-Button-1>", lambda e: self.open_dashboard())
        c.bind("<Button-3>", self._show_menu)
        self.root.bind("<Escape>", lambda e: self.quit())

    def _drag_start(self, event) -> None:
        self._dx, self._dy = event.x, event.y
        self._moved = False

    def _drag_move(self, event) -> None:
        self._moved = True
        x = self.root.winfo_x() + event.x - self._dx
        y = self.root.winfo_y() + event.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def _place(self, x: int, y: int, snap: bool = False) -> None:
        """Pencereyi konumlandirir; ekran disina tasmaz, istege bagli yapisir."""
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = self.root.winfo_width() or WIDGET_W
        h = self.root.winfo_height() or 64

        if snap:
            # Kenara SNAP_PX'ten yakinsa tam yapistir. Boylece widget
            # ekranin kenarinda duzgun durur, elle piksel piksel
            # hizalamaya gerek kalmaz.
            if x <= SNAP_PX:
                x = 0
            elif x + w >= sw - SNAP_PX:
                x = sw - w
            if y <= SNAP_PX:
                y = 0
            elif y + h >= sh - SNAP_PX:
                y = sh - h

        # Her durumda gorunur alanda kal
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        self.root.geometry(f"+{x}+{y}")

    def _drag_end(self, event) -> None:
        if not getattr(self, "_moved", False):
            return
        self._place(self.root.winfo_x(), self.root.winfo_y(), snap=True)
        self.settings["x"] = self.root.winfo_x()
        self.settings["y"] = self.root.winfo_y()
        save_settings(self.settings)

    def _build_menu(self) -> None:
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Panoyu aç", command=self.open_dashboard)
        m.add_separator()

        boyut = tk.Menu(m, tearoff=0)
        for mod in MODES:
            boyut.add_command(
                label=MODE_LABELS[mod],
                command=lambda mo=mod: self.set_mode(mo),
            )
        m.add_cascade(label="Boyut", menu=boyut)

        m.add_command(label="Temayı değiştir", command=self.toggle_theme)
        m.add_command(label="Saydamlık +", command=lambda: self.nudge_alpha(+0.06))
        m.add_command(label="Saydamlık −", command=lambda: self.nudge_alpha(-0.06))
        m.add_separator()
        m.add_command(label="Kapat", command=self.quit)
        self.menu = m

    def _show_menu(self, event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ---------------- eylemler ----------------

    def open_dashboard(self) -> None:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{self.port}/")

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            return
        self.mode = mode
        self.settings["mode"] = mode
        save_settings(self.settings)
        self.draw()
        # Boy degisince alt kenar kaydi; yapisik duruyorsa yeniden hizala.
        self.root.update_idletasks()
        self._place(self.root.winfo_x(), self.root.winfo_y(), snap=True)

    def toggle_theme(self) -> None:
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.colors = PALETTE[self.theme_name]
        self.canvas.config(bg=self.colors["bg"],
                           highlightbackground=self.colors["border"])
        self.settings["theme"] = self.theme_name
        save_settings(self.settings)
        self.draw()

    def nudge_alpha(self, delta: float) -> None:
        try:
            cur = float(self.root.attributes("-alpha"))
        except Exception:
            cur = 0.94
        new = max(0.35, min(1.0, cur + delta))
        self.root.attributes("-alpha", new)
        self.settings["alpha"] = new
        save_settings(self.settings)

    def quit(self) -> None:
        # Sunucuyu biz baslattiysak biz kapatiriz; kullanici baslattiysa dokunmayiz.
        if self.server_proc and self.server_proc.poll() is None:
            try:
                self.server_proc.terminate()
            except Exception:
                pass
        self.root.destroy()

    def _start_server(self) -> None:
        if self.server_proc and self.server_proc.poll() is None:
            return
        try:
            flags = 0
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.server_proc = subprocess.Popen(
                [sys.executable, str(APP_DIR / "server.py"),
                 "--port", str(self.port), "--no-browser"],
                cwd=str(APP_DIR), creationflags=flags,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            self.server_proc = None

    # ---------------- veri ----------------

    def fetch(self) -> None:
        url = f"http://127.0.0.1:{self.port}/api/status"
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.cards = data.get("cards") or []
            self.offline = False
        except (urllib.error.URLError, OSError, ValueError):
            self.offline = True
            if self.autostart:
                self._start_server()

    def tick(self) -> None:
        self.fetch()
        self.draw()
        self.root.after(RETRY_MS if self.offline else REFRESH_MS, self.tick)

    # ---------------- cizim ----------------

    def _color(self, card: dict) -> str:
        sev = str(card.get("severity") or "").lower()
        if sev == "critical":
            return self.colors["danger"]
        if sev == "warning":
            return self.colors["warn"]
        if sev == "normal":
            return self.colors["ok"]
        pct = card.get("percent") or 0
        if pct >= 90:
            return self.colors["danger"]
        if pct >= 70:
            return self.colors["warn"]
        return self.colors["ok"]

    def _short(self, card: dict) -> str:
        kind = str(card.get("key", "")).split(":")[0]
        base = SHORT_LABELS.get(kind, kind[:4])
        # weekly_scoped ise model adini goster — asil daraltan o olabilir
        if ":" in str(card.get("key", "")):
            model = str(card["key"]).split(":", 1)[1]
            return model[:5]
        return base

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        col = self.colors

        if self.offline:
            c.config(height=40)
            c.create_text(95, 15, text="sunucu kapalı", fill=col["muted"],
                          font=("Segoe UI", 9))
            c.create_text(95, 29, text="başlatılıyor…" if self.autostart else "çift tık → pano",
                          fill=col["muted"], font=("Segoe UI", 8))
            return

        # Once su an fiilen sinirlayan limit, sonra dolulukta azalan sirayla.
        # Mini modda yalnizca ilki gosterilir — asil merak edilen o.
        cards = [x for x in self.cards if x.get("percent") is not None]
        cards.sort(key=lambda x: (not x.get("is_active"), -(x.get("percent") or 0)))
        cards = cards[:MODE_ROWS.get(self.mode, 3)]

        row_h = 20
        height = max(28, len(cards) * row_h + 8)
        c.config(height=height)

        for i, card in enumerate(cards):
            y = 4 + i * row_h
            pct = float(card.get("percent") or 0)
            color = self._color(card)

            # etiket
            c.create_text(6, y + 9, text=self._short(card), anchor="w",
                          fill=col["muted"], font=("Segoe UI", 8))
            # cubuk
            bx0, bx1 = 44, 148
            c.create_rectangle(bx0, y + 5, bx1, y + 13, fill=col["track"], width=0)
            filled = bx0 + (bx1 - bx0) * min(100.0, pct) / 100.0
            if filled > bx0:
                c.create_rectangle(bx0, y + 5, filled, y + 13, fill=color, width=0)
            # yuzde
            c.create_text(184, y + 9, text=f"{pct:.0f}%", anchor="e",
                          fill=col["fg"], font=("Segoe UI", 9, "bold"))
            # aktif limit isareti
            if card.get("is_active"):
                c.create_rectangle(1, y + 3, 3, y + 15, fill=color, width=0)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Claude kota widget'i (masaustu)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8110")))
    parser.add_argument("--theme", default=settings.get("theme", "dark"),
                        choices=["dark", "light"])
    parser.add_argument("--autostart", action="store_true", default=True,
                        help="Sunucu kapaliysa kendisi baslatir (varsayilan acik)")
    parser.add_argument("--no-autostart", dest="autostart", action="store_false")
    parser.add_argument("--mode", default=settings.get("mode", "full"),
                        choices=list(MODES),
                        help="full = 3 satir, compact = 2, mini = yalnizca "
                             "su an sinirlayan limit")
    args = parser.parse_args()

    Widget(args.port, args.theme, args.autostart, args.mode).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
