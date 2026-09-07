"""Renk paleti — TEK gercek kaynak.

Bu dosya neden var: gece boyunca ayni renkler uc yerde ayri ayri yaziliydi
(web/style.css, widget.py, tools/contrast_check.py). Bir yerde duzeltip
digerlerini unutmak kacinilmazdi ve oldu da. Artik:

  * widget.py            -> buradan okur
  * tools/contrast_check -> buradan okur ve olcer
  * web/style.css        -> elle yazilir AMA tests/test_consistency.py
                            her degerin buradakiyle ayni oldugunu dogrular

Iki renk ailesi, bilincli ayrim:
  *      -> GOSTERGE rengi (cubuk dolgusu, halka). WCAG esigi 3:1.
  *-ink  -> METIN rengi (rozet yazisi).           WCAG esigi 4.5:1.

Degerleri degistirirken: once burada degistir, sonra style.css'i eslestir,
sonra `python tools/contrast_check.py` ile olc, sonra testleri kos.
"""

from __future__ import annotations

LIGHT: dict[str, str] = {
    "bg": "#f6f7f9",
    "surface": "#ffffff",
    "surface-2": "#f0f2f5",
    "border": "#e2e5ea",
    "fg": "#1b1e23",
    "fg-muted": "#666e7a",
    "track": "#e6e9ee",
    "accent": "#c96442",
    "ok": "#197f45",
    "warn": "#a85f08",
    "danger": "#c62f2f",
    "accent-ink": "#9c4527",
    "ok-ink": "#0f5c31",
    "warn-ink": "#7a4405",
    "danger-ink": "#96201f",
}

DARK: dict[str, str] = {
    "bg": "#14161a",
    "surface": "#1c1f25",
    "surface-2": "#22262d",
    "border": "#2d323b",
    "fg": "#e6e8ec",
    "fg-muted": "#9aa3b0",
    "track": "#2b3038",
    "accent": "#e07a52",
    "ok": "#3fb56b",
    "warn": "#e09a3a",
    "danger": "#e05e5e",
    "accent-ink": "#f0a184",
    "ok-ink": "#6ee7a3",
    "warn-ink": "#f5c274",
    "danger-ink": "#ff9d9d",
}

# style.css'te light-dark() icinde gecmesi beklenen jetonlar. --shadow ve
# --radius renk degil, bu yuzden esleme disinda.
CSS_TOKENS = tuple(LIGHT.keys())


def widget_palette(theme: str) -> dict[str, str]:
    """tkinter widget'inin kullandigi daraltilmis anahtar kumesi.

    Widget'ta rozet metni yok, o yuzden *-ink ailesine ihtiyac duymuyor.
    """
    src = DARK if theme == "dark" else LIGHT
    return {
        "bg": src["surface"],
        "fg": src["fg"],
        "muted": src["fg-muted"],
        "track": src["track"],
        "border": src["border"],
        "ok": src["ok"],
        "warn": src["warn"],
        "danger": src["danger"],
    }
