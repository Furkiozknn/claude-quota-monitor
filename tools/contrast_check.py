"""WCAG kontrast denetimi.

Paletteki renk ciftlerinin kontrast oranini olcer ve WCAG 2.2 AA esiklerine
gore gecti/kaldi raporlar. Goz karariyla "yeterince koyu duruyor" demek
yerine olcuyoruz.

Esikler
-------
* Normal metin        : 4.5:1
* Buyuk metin (>=18pt): 3.0:1
* Arayuz bileseni     : 3.0:1  (cubuklar, kenarliklar, odak halkasi)

Rozetlerde metin, kendi renginin surface uzerine %16-20 karistirilmis
halinin uzerinde duruyor. Bu yuzden dumduz "renk vs surface" degil,
gercekte olusan bilesik arka plan hesaplaniyor.

Calistirma:  python tools/contrast_check.py
Cikis kodu:  0 hepsi gecti, 1 kalan var
"""

from __future__ import annotations

import sys

AA_TEXT = 4.5
AA_LARGE = 3.0
AA_UI = 3.0

# Iki ayri renk ailesi var ve bu bilincli bir ayrim:
#   *      -> GOSTERGE rengi (cubuk dolgusu, halka). Esik 3:1.
#   *-ink  -> METIN rengi (rozet yazisi). Esik 4.5:1.
# Ayni rengi ikisinde de kullanmak, rozet metnini kendi soluk arka planinin
# uzerinde okunmaz birakiyordu.
LIGHT = {
    "bg": "#f6f7f9", "surface": "#ffffff", "surface-2": "#f0f2f5",
    "border": "#e2e5ea", "fg": "#1b1e23", "fg-muted": "#666e7a",
    "accent": "#c96442", "ok": "#197f45", "warn": "#a85f08",
    "danger": "#c62f2f", "track": "#e6e9ee",
    "ok-ink": "#0f5c31", "warn-ink": "#7a4405", "danger-ink": "#96201f",
    "accent-ink": "#9c4527",
}

DARK = {
    "bg": "#14161a", "surface": "#1c1f25", "surface-2": "#22262d",
    "border": "#2d323b", "fg": "#e6e8ec", "fg-muted": "#9aa3b0",
    "accent": "#e07a52", "ok": "#3fb56b", "warn": "#e09a3a",
    "danger": "#e05e5e", "track": "#2b3038",
    "ok-ink": "#6ee7a3", "warn-ink": "#f5c274", "danger-ink": "#ff9d9d",
    "accent-ink": "#f0a184",
}


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = (_channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def mix(fg: str, bg: str, pct: float) -> str:
    """color-mix(in srgb, fg pct%, bg) — CSS'teki rozet arka planinin karsiligi."""
    f, b = _rgb(fg), _rgb(bg)
    out = tuple(round(255 * (f[i] * pct + b[i] * (1 - pct))) for i in range(3))
    return "#%02x%02x%02x" % out


def check(tema_adi: str, p: dict[str, str]) -> list[tuple]:
    """(aciklama, on, arka, oran, esik, gecti) listesi doner."""
    rows: list[tuple] = []

    def add(desc, fg, bg, thr):
        ratio = contrast(fg, bg)
        rows.append((desc, fg, bg, ratio, thr, ratio >= thr))

    # Govde metni
    add("gövde metni (fg / surface)", p["fg"], p["surface"], AA_TEXT)
    add("gövde metni (fg / bg)", p["fg"], p["bg"], AA_TEXT)
    add("ikincil metin (fg-muted / surface)", p["fg-muted"], p["surface"], AA_TEXT)
    add("ikincil metin (fg-muted / bg)", p["fg-muted"], p["bg"], AA_TEXT)

    # Rozet metni: *-ink rengi, gosterge renginin %18 karisiminin uzerinde
    for ad, oran in (("ok", 0.16), ("warn", 0.20), ("danger", 0.18)):
        arka = mix(p[ad], p["surface"], oran)
        add(f"rozet metni ({ad}-ink / {ad} %{int(oran*100)} karışım)",
            p[f"{ad}-ink"], arka, AA_TEXT)

    # Arayuz bilesenleri — 3:1 yeterli
    for ad in ("accent", "warn", "danger", "ok"):
        add(f"çubuk dolgusu ({ad} / track)", p[ad], p["track"], AA_UI)
    add("odak halkası (accent / surface)", p["accent"], p["surface"], AA_UI)

    # Not: kart kenarligi bilinçli olarak denetlenmiyor. WCAG 1.4.11 durum
    # bildiren arayuz bilesenleri icin gecerli; iki benzer yuzeyi ayiran
    # dekoratif cizgi kapsam disi. 3:1'e zorlamak paneli kutu kutu yapardi.

    return rows


def main() -> int:
    kalan = 0
    for tema_adi, palet in (("AÇIK", LIGHT), ("KOYU", DARK)):
        print(f"\n=== {tema_adi} TEMA ===")
        for desc, fg, bg, ratio, thr, ok in check(tema_adi, palet):
            mark = "gecti" if ok else "KALDI"
            if not ok:
                kalan += 1
            print(f"  [{mark}] {ratio:5.2f}:1  (esik {thr})  {desc}")
            if not ok:
                print(f"           {fg} uzerine {bg}")

    print(f"\nToplam kalan: {kalan}")
    return 0 if kalan == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
