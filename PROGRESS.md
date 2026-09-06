# İlerleme Günlüğü

Bu dosya otonom çalışmanın hafızası. Her turda önce bu okunur, sonra
"Sıradaki işler"den en üstteki madde yapılır, sonuç buraya yazılır.

**Kapsam:** yalnızca `D:\Repolar\claude-quota-monitor`. Başka projeye
dokunulmaz.

**Sınır:** GitHub'a yayınlama yok — `raporlar/ONAY-BEKLEYENLER.md` madde 1'de
onay bekliyor. Yerel git commit'i serbest.

---

## Sıradaki işler (öncelik sırası)

1. **Testler** — `normalize()` için gerçek şema örnekleriyle birim testler.
   Şema değişirse hemen anlaşılsın.
2. **Kontrast denetimi** — palet renklerinin WCAG AA oranlarını ölç ve
   gerekirse düzelt. Yüksek kontrast modu ekle.
3. **LICENSE + ekran görüntüleri** — paylaşıma hazırlık.
4. **Widget iyileştirmeleri** — kenara yapışma, daha kompakt mod.
5. **Çoklu görünüm** — anlık / günlük / aylık.
6. **Provenance etiketleme** — her sayının kaynağını açıkça işaretle.
7. **Windows açılışta başlatma** — Başlangıç klasörüne kısayol
   (kayıt defteri değil; geri alınabilir olsun).

---

## Tamamlananlar

### v0.7.0 — Eşik bildirimi · 7 Eylül, gece
- `notify.py` — **bağımlılıksız** Windows bildirimi. `win10toast`/`plyer`
  kullanılmadı; projenin sıfır bağımlılık sözü bildirim için de geçerli.
  PowerShell üzerinden WinRT toast, olmazsa NotifyIcon balonu.
- PowerShell'e script stdin'den veriliyor — tırnak/ters bölü kaçışıyla
  uğraşılmıyor (bu makinede bilinen bir tuzak).
- `--notify-at` bayrağı, varsayılan %90, `0` = kapalı.
- **Gece yarısı inceliği:** ilk başarılı sorguda bildirim atılmaz, yalnızca
  mevcut durum kaydedilir (`_seeded`). Yoksa program her açıldığında zaten
  dolu olan pencereler için bildirim yağardı.
- Pencere başına tek bildirim; sıfırlanıp yüzde 5 puan altına düşünce
  yeniden hak kazanır — eşiğin tam üstünde salınan değer bildirim yağmuru
  yaratmasın diye.
- Gönderim ayrı iş parçacığında; PowerShell birkaç saniye sürebiliyor,
  poller beklemesin.

Doğrulandı: gerçek bildirim gönderildi (WinRT yolu, çıkış kodu 0).
Görsel olarak doğrulanamadı — ekran görülemiyor.

### v0.6.0 — Terminal çıktısı · 7 Eylül, gece
- `--once` (okunakli özet) ve `--compact` (tek satır, statusline için).
  Sunucu başlatmaz, veritabanı açmaz, hemen çıkar.
- **Nazik olma korundu:** önce çalışan sunucuya bakar, ondan okur — uca
  **ek sorgu gitmez**. Sunucu kapalıysa tek bir doğrudan sorgu.
- Simgeler: `!` kritik, `*` dikkat, `<` şu an sınırlayan limit.
- Betiklerde kullanılsın diye anlamlı çıkış kodları (0/2/3/4).
- README'ye örnek çıktılarla eklendi.

Doğrulandı: her iki mod da gerçek veriyle çalıştı, çıkış kodu 0.

### v0.5.0 — Erişilebilirlik ve güvenlik geçişi · 6 Eylül, gece
UI/UX araştırması yapıldı; üç somut eksik bulundu ve kapatıldı.

- **Durum artık yalnızca renkle anlatılmıyor.** WCAG'in en sık ihlal edilen
  kuralı buydu. Her kartta renk + **simge** (● ▲ ■) + **metin**
  (normal / dikkat / kritik) birlikte. Renk körlüğünde de okunur.
- **Doğrusal kıyas çubuğu eklendi.** Araştırmanın net bulgusu: insan gözü
  eğri değil düz çizgileri kıyaslamada iyi. Halka görsel kimlik olarak
  kaldı, hizalı çubuk kıyas için eklendi.
- **Klavye gezinmesi.** Sekmeler `role="tab"` + roving tabindex + ok
  tuşları / Home / End. Panellere `role="tabpanel"`, uyarı şeridine
  `aria-live="polite"`, çubuklara `role="progressbar"` + `aria-valuenow`.
  Görünür `:focus-visible` halkası.
- **XSS yüzeyi kapatıldı.** Kart etiketleri belgelenmemiş bir uçtan gelip
  `innerHTML`'e basılıyordu. `esc()` eklendi — ucun bugün markup
  döndürmemesi yarın döndürmeyeceği anlamına gelmez.

Doğrulandı: `node --check` temiz, sayfa/statikler HTTP 200, ARIA işaretleri
yayınlanan HTML'de mevcut.

### v0.4.1 — Paylaşıma hazırlık başlangıcı · 6 Eylül
- `git init` + ilk commit (`4341cd1`), 8 dosya / 1946 satır. `.gitignore`.
- Widget masaüstünde doğrulandı.
- **Not:** kullanıcının otomasyonu aynı gece günlük 8 USD maliyet tavanına
  takıldı. Tavan yükseltilmedi — `ONAY-BEKLEYENLER.md` madde 3.

### v0.4.0 — Masaüstü widget'i · 6 Eylül
- `widget.py` — tkinter (stdlib), çerçevesiz, her zaman üstte, sürüklenebilir.
- **Mimari karar:** widget Anthropic'e istek atmaz, yerel sunucudan okur.
  Tek veri kaynağı, çift sorgu yok, nazik olma politikası korunur.
- Konum/tema/saydamlık `~/.claude/quota-widget.json`'a kaydediliyor.

### v0.3.0 — Yanma hızı · 6 Eylül
- SQLite geçmişinden %/saat eğimi. Pencere sıfırlanınca yüzde düştüğü için
  yalnızca son sıfırlanmadan bu yanaki yükseliş ölçülüyor.
- Asıl soruyu cevaplıyor: *pencere sıfırlanmadan önce dolar mıyım?*
- Çalıştığı doğrulandı: oturum %13.93/sa, haftalık %1.27/sa.

### v0.2.0 — Ayrıştırıcı düzeltmesi · 6 Eylül
- Ham JSON gerçek şemayı gösterdi; ilk sürüm 4 kart üretiyordu, ikisi çöptü.
- **Bulgu:** yanıtta düzgün yapılı bir `limits` dizisi var —
  `kind`/`group`/`percent`/`severity`/`resets_at`/`scope`/`is_active`.
  Birincil kaynak yapıldı. **Severity uydurulmuyor, uçtan alınıyor.**
- Uç, yayınlanmamış özelliklere ait kod adları döndürüyor (`tangelo`,
  `iguana_necktie`, `cinder_cove`, `copper_kite`, `amber_ladder`,
  `juniper_tide`, `omelette`). Eleniyor.
- Eski gezinme mantığı şema değişirse diye yedek yol olarak korundu.

### v0.1.0 — İlk çalışan sürüm · 6 Eylül
- `server.py` — nazik poller (180 sn, backoff max 900 sn, **token rotasyonu
  yok**), SQLite geçmiş, yalnızca `127.0.0.1`.
- Resmi `/api/oauth/usage` ucundan gerçek kota verisi. Doğrulandı: HTTP 200.
- Web panosu: 4 sekme, açık-koyu tema, halka grafik, canvas çizgi grafiği.
  Bağımlılık yok.

---

## Bilinen riskler

- `/api/oauth/usage` **belgelenmemiş**. Anthropic haber vermeden
  değiştirebilir. Yedek ayrıştırıcı, `esc()` ve Ham veri sekmesi bu yüzden var.
- Yanma hızı en az ~5 dakikalık kesintisiz örnekleme ister; sunucu sık
  yeniden başlatılırsa "veri birikiyor" der.
