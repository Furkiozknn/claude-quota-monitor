# İlerleme Günlüğü

Bu dosya otonom çalışmanın hafızası. Her turda önce bu okunur, sonra
sıradaki en değerli iş seçilir, sonuç buraya yazılır.

**Kapsam:** yalnızca `D:\Repolar\claude-quota-monitor`. Başka projeye
dokunulmaz.

**Sınır:** GitHub'a yayınlama yok — `raporlar/ONAY-BEKLEYENLER.md` madde 1'de
onay bekliyor. Yerel git commit'i serbest.

---

## Tamamlananlar

### 6 Eylül 2026 — v0.1.0 · İlk çalışan sürüm
- `server.py` — nazik poller (180 sn, backoff max 900 sn, **token rotasyonu
  yok**), SQLite geçmiş, HTTP sunucu, `127.0.0.1` bağlanma.
- Resmi `/api/oauth/usage` ucundan gerçek kota verisi alındı. Doğrulandı:
  HTTP 200, abonelik `max`.
- Web panosu: 4 sekme (Kotalar / Geçmiş / Ham veri / Tanılama), açık-koyu
  tema, halka grafikler, canvas çizgi grafiği. Bağımlılık yok.

### 6 Eylül 2026 — v0.2.0 · Ayrıştırıcı düzeltmesi
- Ham JSON gerçek şemayı gösterdi. İlk sürüm 4 kart üretiyordu, ikisi çöptü
  (`nimbus_quill`, `spend`).
- **Bulgu:** cevapta düzgün yapılı bir `limits` dizisi var —
  `kind` / `group` / `percent` / `severity` / `resets_at` / `scope` /
  `is_active`. Bu birincil kaynak yapıldı.
- **Severity artık uydurulmuyor**, uçtan alınıyor.
- Uç, yayınlanmamış özelliklere ait kod adları döndürüyor (`tangelo`,
  `iguana_necktie`, `cinder_cove`, `copper_kite`, `amber_ladder`,
  `juniper_tide`, `omelette`). Bunlar eleniyor.
- Eski gezinme mantığı şema değişirse diye yedek yol olarak korundu.
- `extra_usage` ve `spend` kota kartı değil, ayrı meta bilgi oldu.

### 6 Eylül 2026 — v0.3.0 · Yanma hızı
- SQLite geçmişinden %/saat eğimi. Pencere sıfırlanınca yüzde düştüğü için
  yalnızca son sıfırlanmadan bu yanaki yükseliş ölçülüyor.
- Asıl soruyu cevaplıyor: *pencere sıfırlanmadan önce dolar mıyım?*

### 6 Eylül 2026 — v0.4.0 · Masaüstü widget'i
- `widget.py` — tkinter (stdlib), çerçevesiz, her zaman üstte, sürüklenebilir.
- **Mimari karar:** widget Anthropic'e istek atmaz, yerel sunucudan okur.
  Tek veri kaynağı, çift sorgu yok, nazik olma politikası korunur.
- Konum/tema/saydamlık `~/.claude/quota-widget.json`'a kaydediliyor.
- Sağ tık menüsü, çift tık → pano, sunucu kapalıysa kendi başlatır.

---

## Sıradaki işler (öncelik sırası)

Her tur en üstteki yapılabilir maddeyi al.

1. **UI/UX araştırma turu + tasarım geçişi** — kota panoları, ilerleme
   göstergeleri, renk erişilebilirliği. Araştır, ilham al, uygula.
2. **`--once` / `--compact` terminal çıktısı** — tarayıcı açmadan tek satır
   durum. Kullanıcının asıl derdi ekran yeriydi.
3. **Eşik bildirimi** — %90'ı geçince Windows bildirimi (stdlib ile).
4. **Testler** — `normalize()` için gerçek şema örnekleriyle birim testler.
   Şema değişirse hemen anlaşılsın.
5. **LICENSE + ekran görüntüleri** — paylaşıma hazırlık.
6. **Erişilebilirlik** — kontrast oranları, klavye navigasyonu, ekran
   okuyucu etiketleri.
7. **Widget iyileştirmeleri** — kenara yapışma, tıklama geçirgenliği,
   daha da kompakt mod.
8. **Çoklu görünüm** — anlık / günlük / aylık.
9. **Provenance etiketleme** — her sayının kaynağını açıkça işaretle
   (`official` vs `estimate`).
10. **Windows açılışta başlatma** — kayıt defteri değil, Başlangıç klasörüne
    kısayol (geri alınabilir).

## Bilinen riskler

- `/api/oauth/usage` **belgelenmemiş**. Anthropic haber vermeden
  değiştirebilir. Yedek ayrıştırıcı ve Ham veri sekmesi bu yüzden var.
- Yanma hızı en az ~5 dakikalık kesintisiz örnekleme ister; sunucu sık
  yeniden başlatılırsa "veri birikiyor" der.
