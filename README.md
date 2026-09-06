# claude-quota-monitor

Claude'un **resmi** kota verisini yerel bir web panosunda gösterir: 5 saatlik
oturum penceresi, haftalık pencere, sıfırlanma geri sayımları ve 24 saatlik
geçmiş grafiği.

Ekranda sürekli yer kaplamaz — istediğinde tarayıcıda açarsın.

## Neden

Mevcut araçlar ikiye ayrılıyor:

| | Resmi kota % | Şık arayüz | Ekran yeri |
|---|---|---|---|
| Tray / taskbar uygulamaları | ✅ | ❌ | Yer kaplar |
| Yerel analiz panoları (ccusage, token-dashboard) | ❌ sadece tahmini maliyet | ✅ | Sıfır |
| **Bu** | ✅ | ✅ | Sıfır |

`ccusage` ve benzerleri yerel JSONL loglarından **tahmini maliyet** hesaplar —
üç farklı araç aynı veriden üç farklı rakam üretebiliyor. Bu araç ise
Claude Code'un kendi kullandığı uçtan **gerçek kullanım yüzdesini** okur.

## Nazik olma politikası

Bu bölüm tasarımın merkezinde; hafife alma.

- **Sorgu aralığı** varsayılan **180 sn**. 60 sn'nin altına *inilemez*.
- **Hata durumunda** üstel backoff, en fazla **900 sn**.
- **Token rotasyonu yapılmaz.** `/api/oauth/usage` ucu token başına ~5 istekle
  sınırlı. Bazı araçlar limite çarpınca yeni OAuth token üretip sayacı
  sıfırlıyor — bu, Anthropic'in kendi hesabına koyduğu kötüye kullanım
  önlemini bilerek devre dışı bırakmak demek ve hesap işaretlenmesi riski
  taşır. Bu araç limite çarpınca **bekler** ve son bilinen değeri göstermeye
  devam eder.
- **Kimlik dosyası yalnızca okunur**, asla yazılmaz. Token'ın süresi dolmuşsa
  yenilemeye çalışmaz; sana "Claude Code'da bir komut çalıştır" der.
- **Ağ:** dışarı giden tek istek `api.anthropic.com`. Telemetri yok, hesap yok.
- **Bağlanma:** yalnızca `127.0.0.1`.

## Kurulum

Bağımlılık yok. Python 3.8+ yeterli.

```bash
python server.py
```

Windows'ta Python PATH'te değilse:

```powershell
& "C:\Users\<sen>\.local\bin\python3.12.exe" server.py
```

Pano `http://127.0.0.1:8110` adresinde açılır.

### Seçenekler

| Bayrak | Varsayılan | Açıklama |
|---|---|---|
| `--once` | — | Sunucu başlatma, durumu yazdır ve çık |
| `--compact` | — | Tek satır çıktı (statusline için). `--once` ima eder |
| `--port` | `8110` | Dinlenecek port (`PORT` değişkeni de olur) |
| `--interval` | `180` | Sorgu aralığı (sn), alt sınır 60 |
| `--db` | `~/.claude/quota-monitor.db` | Geçmiş veritabanı |
| `--no-browser` | — | Tarayıcıyı otomatik açma |
| `--host` | `127.0.0.1` | Değiştirmen önerilmez |

### Terminalden hızlı bakış

Tarayıcı açmadan, hatta sunucu çalışmadan:

```bash
$ python server.py --once
Claude kota — max
  Haftalık — Kapsamlı · Fable    [##########] 100%  KRITIK  sifir: 1s44dk  <
  Haftalık — Tüm modeller        [#########.]  86%  dikkat  sifir: 1s44dk
  5 Saatlik Oturum               [#######...]  68%  normal  sifir: 1s24dk
  kaynak: yerel sunucu

$ python server.py --compact
Fable 100%! | 7g 86%* | 5s 68%
```

`!` = kritik, `*` = dikkat, `<` = şu an seni fiilen sınırlayan limit.

**Önemli:** Bu mod önce çalışan sunucuya bakar. Sunucu ayaktaysa ondan okur
ve uca **ek sorgu gitmez** — nazik olma politikası korunur. Sunucu kapalıysa
tek bir doğrudan sorgu yapar.

Çıkış kodları: `0` başarılı, `2` token yok, `3` uç hata döndü, `4` kota
bilgisi bulunamadı. Betiklerden kullanışlı.

## Arayüz

- **Kotalar** — her pencere için halka grafik, yüzde, sıfırlanma geri sayımı.
  %70'te turuncu, %90'da kırmızı.
- **Geçmiş** — son 24 saatin çizgi grafiği. Sıfıra düşen yerler pencerenin
  sıfırlandığı anlar.
- **Ham veri** — uçtan gelen JSON, olduğu gibi.
- **Tanılama** — HTTP durumu, son deneme, backoff durumu, politika özeti.

## Ham veri sekmesi neden var

`/api/oauth/usage` **belgelenmemiş** bir uç. Anthropic'in genel API
referansında yok; Claude Code kendi arayüzü için kullanıyor. Şeması haber
verilmeden değişebilir.

Bu yüzden `normalize()` şekle bağımlı yazılmadı: gelen JSON'da yüzde ve
sıfırlanma benzeri alanları arayıp bulduğunu karta çevirir, hem iç içe hem
düzleştirilmiş şemaları dener. Hiçbir şey tanıyamazsa kartlar boş kalır ama
ham JSON her zaman durur — oradan bakıp ayrıştırıcı güncellenir.

## Veri nereye yazılır

Tek yazılan yer `~/.claude/quota-monitor.db` (SQLite, geçmiş grafiği için).
Silersen sadece geçmiş gider, araç çalışmaya devam eder.

## Bilinen sınırlar

- Uç belgelenmemiş; şeması değişirse ayrıştırıcı güncellenmeli.
- Yalnızca abonelik (Pro/Max) kotasını gösterir. API anahtarıyla kullanımı
  kapsamaz.
- Anthropic kesin token sayısı yayınlamıyor — gösterilen şey pencerelerin
  **yüzdesi**, "şu kadar token kaldı" değil.

## Lisans

MIT
