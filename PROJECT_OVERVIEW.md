# POKO — Proje ve Menü Özeti

Bu doküman POKO'nun ne olduğunu, kimin ne gördüğünü ve sidebar'daki her menünün gerçekte
neye bağlı olduğunu (gerçek özellik mi, henüz placeholder mı) özetler. Deploy/altyapı
detayları için `README.md`, tasarım sistemi için `DESIGN.md`, kod/agent kuralları için
`CLAUDE.md`'ye bakın — bu dosya onların yerine değil, tamamlayıcısı.

## POKO nedir

POKO, inşaat projelerinde Primavera P6 programlarını temel alan, çok-kiracılı
(multi-tenant) bir **schedule-update ve analiz** platformu. İki ayrı katmanı var:

1. **Update workflow** (proje başında planlanan çekirdek): admin periyodik bir update
   penceresi açar → her taşeron sadece kendi scope'undaki activity'leri günceller
   (% tamamlanma / tarih / kalan süre anında kaydedilir; mantık/lag/bağımlılık değişikliği
   admin onayına düşer) → admin pencereyi kapatır.
2. **P6 analiz motoru** (bu oturumda taşınan kısım): bir arkadaşın yazdığı, gerçek
   CPM/DCMA/EVM/Monte Carlo/Logic Diff/XER motorlarına sahip tek-kiracılı masaüstü
   uygulamasından, bu projenin çok-kiracılı Postgres+RLS mimarisine **birebir kod
   kopyalanmadan, mantığı korunarak yeniden yazılıp** taşındı.

Bu iki katman aynı `activities`/`activity_relationships` tablosu üzerinde çalışıyor —
taşeronun scope sayfasında düzenlediği satırlar, XER import'un yazdığı CPM alanlarıyla
aynı satırlar.

## Rol yapısı

| Rol | Kim | Ne görür |
|---|---|---|
| **Platform Admin** | POKO ekibi | `/platform-admin` konsolu — tenant (şirket) oluşturma, başka platform admin ekleme, kullanım istatistikleri. Şirket içi hiçbir veriye dokunmaz. |
| **Company Admin** | Şirketin admini | Sidebar'daki her şey, sınırsız proje erişimi, kullanıcı yönetimi, baseline kilitleme/açma gibi kritik işlemler |
| **Company Employee** | Şirket çalışanı | `project_roles`'a göre değişir (Project Administrator / All Access / Execution / User Management / Activity Status Updater) — bazı menüler bu role bağlı görünür/gizlenir |
| **Subcontractor** | Taşeron | Sidebar bile yok — ayrı, tek sayfalık minimal arayüz (`/scope`), sadece kendisine atanmış scope'u, sadece açık update period'da |

## Company Admin/Employee sidebar'ı (4 grup, 14 menü)

### Analyze
| Menü | Durum | Ne yapar |
|---|---|---|
| **Dashboard** | ✅ Gerçek | Aktif update period, taşeron submission durumu, bekleyen flag sayısı |
| **Schedule** | ✅ Gerçek | Tüm activity'lerin tablo görünümü — tarih, float, kritik yol, arama/sayfalama |
| **Gantt** | ✅ Gerçek | El yapımı CSS bar Gantt — kritik/durum renklendirme, data-date çizgisi, 3 zoom seviyesi |
| **EVM / S-Curve** | ✅ Gerçek | Baseline kilitleme, SPI/CPI/EAC/TCPI KPI kartları, S-Curve grafiği, Excel export |

### Validate
| Menü | Durum | Ne yapar |
|---|---|---|
| **DCMA 14-Point** | ✅ Gerçek | DCMA EA PAM 200.1'in 14 kontrolü, skor kartı, sorunlu activity listesi |
| **Risk Analysis** | ✅ Gerçek | Monte Carlo simülasyonu (triangular dağılım) — P10/P50/P80/P90 bitiş tarihi, histogram |
| **Logic Diff** | ✅ Gerçek | İki XER import arasında eklenen/silinen/değişen ilişkileri karşılaştırır |

### Manage
| Menü | Durum | Ne yapar |
|---|---|---|
| **Progress Input** | ✅ Gerçek | WBS'e göre gruplanmış activity listesi, günlük "yakılan adam-saat" girişi (EVM'i besler) |
| **Completion Plan** | ⏳ Placeholder | Henüz kodlanmadı |
| **Project Files** | ✅ Gerçek | .xer dosyası yükleme (sürükle-bırak), geçmiş import listesi |
| **Update Period Control** | ⏳ Placeholder (backend hazır) | Backend'de period açma/kapama/hatırlatma zaten çalışıyor (`/update-periods`), bu sayfa henüz o API'ye bağlanmadı |
| **Export / Sync to P6** | ✅ Gerçek | Güncel schedule'ı .xer olarak indirir (P6'da F9 çalıştırıp geri yükleme akışı için) |

### Team
| Menü | Kim görür | Ne yapar |
|---|---|---|
| **User Management** | company_admin, veya `user_management`/`project_administrator` proje rolüne sahip employee | Kullanıcı/davet/proje/taşeron organizasyonu yönetimi |
| **Change Review Queue** | sadece company_admin | Taşeronların bayrakladığı mantık/lag değişikliklerini onaylama/reddetme |

## Subcontractor arayüzü

Sidebar'sız, tek sayfa (`/scope`): sadece kendine atanmış scope'taki activity'ler,
sadece açık bir update period varken düzenlenebilir. Mantık/lag değişikliği yaparsa
admin onayına düşer (Change Review Queue'ya gider).

## Platform Admin konsolu

`/platform-admin/tenants`, `/admins`, `/usage` — POKO ekibinin tenant oluşturduğu,
başka platform admin eklediği, kullanım istatistiklerine baktığı, şirket içi verilere
hiç dokunmayan ayrı bir alan.

## Backend'de olup frontend'de henüz sayfası olmayanlar

Bu API'ler çalışıyor ve test edilmiş durumda, ama sidebar'da karşılık gelen bir sayfa yok
(bilinçli bir kapsam kararı — bkz. son commit mesajları):

- **Quick EVM** (`GET /projects/{id}/evm/quick`) — baseline gerektirmeyen anlık EVM, kaynak
  atamasına (resource assignment) ihtiyaç duyar
- **Metadata editor** (`GET/PATCH /projects/{id}/calendars`, `/resources`, `/activity-codes`)
  — takvim/kaynak/activity code isim düzenleme

## Veri modeli — bu oturumda eklenen tablolar

`calendars`, `schedule_imports`, `wbs_nodes`, `resources`, `resource_assignments`,
`baselines`, `baseline_activities`, `baseline_pv_curve`, `progress_entries`,
`evm_snapshots`, `activity_code_types`, `activity_code_values`, `task_activity_codes`
— hepsi diğer her tenant tablosuyla aynı Postgres RLS izolasyon deseninde
(`backend/alembic/versions/0005`..`0011`).

## Motor modülleri (backend/app/engine/ ve parser/)

| Modül | Ne yapar |
|---|---|
| `parser/` | .xer dosyasını parse eder (TASK, TASKPRED, CALENDAR, PROJWBS, RSRC, TASKRSRC, ACTVTYPE/ACTVCODE/TASKACTV — referans projedeki her tablo) |
| `engine/cpm/` | Takvim-farkında CPM scheduler — forward/backward pass, float, longest-path kritik yol |
| `engine/quality/` | DCMA 14-point kontrol motoru |
| `engine/risk/` | Monte Carlo simülasyonu (numpy'siz, stdlib ile) |
| `engine/diff/` | Logic Diff — iki import'un ilişki karşılaştırması |
| `engine/export/` | XER writer — güncel schedule'ı P6'ya geri yazılabilir formatta üretir |
| `engine/evm/` | Quick EVM + baseline-kilitli S-Curve zaman serisi + Excel export |

## Bilinen sınırlamalar

- **Gerçek P6 ile hiç test edilmedi** — her şey kendi parser'ımızla round-trip testiyle
  doğrulandı (`parse_xer(build_xer(...))` değişmeden dönüyor), ama gerçek Primavera P6
  davranışı henüz doğrulanmadı.
- Activity code / resource / calendar düzenleme için frontend arayüzü yok (API var).
- Completion Plan ve Update Period Control sayfaları henüz boş.
