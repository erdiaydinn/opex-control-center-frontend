# DockOS RC7.5 İç Test ve Go-Live Kontrol Listesi

## İç test kabulü

- [ ] `INSTALL_DOCKOS_RC7_INTERNAL_TEST.ps1` hatasız tamamlandı.
- [ ] `START_DOCKOS_RC7_INTERNAL_TEST.ps1` RC7.5 backend sağlık kontrolünü geçti.
- [ ] `TEST_DOCKOS_RC7_INTERNAL_TEST.ps1` tüm API kontrollerini geçti.
- [ ] Açık ve koyu temada tüm tablo, form, buton ve durum etiketleri okunuyor.
- [ ] PO yükleme ve tedarikçi erişim ekranları masaüstü ve dar ekranda taşmadan, sıkışmadan görüntüleniyor.
- [ ] Türkçe, İngilizce, Almanca ve Arapça ekranlar kontrol edildi; Arapça RTL düzeni bozulmuyor.
- [ ] Tedarikçi e-postaları doğru tedarikçi ve merkez depo kapsamlarıyla eşleştirildi.
- [ ] Akşam/gece slotları başlangıç saati, süre ve blok adediyle oluşturulup kaydedildi.
- [ ] Çok saatli blok açıldığında çakışan saatlik slotların kaldırıldığı ve tedarikçide tek randevu seçeneği kaldığı doğrulandı.
- [ ] Sonradan yeni blok ekleme ve gece yarısını geçen slot senaryosu test edildi.
- [ ] Rezervasyon oluşturma, merkez depo düzenleme/iptal ve 48/24 saat bildirim akışı test edildi.

## Yayını engelleyen zorunlu maddeler

- [ ] Şirket sunucusu veya onaylı cloud servisi tahsis edildi.
- [ ] HTTPS domain ve TLS sertifikası hazır.
- [ ] OPEX oturumunu doğrulayan gateway/reverse proxy kuruldu; `X-DockOS-Gateway` yalnızca gateway tarafından ekleniyor.
- [ ] En az 32 karakter rastgele `DOCKOS_GATEWAY_SECRET` tanımlandı ve tarayıcı koduna konmadı.
- [ ] `DOCKOS_TRUST_ROLE_HEADER=false` olarak bırakıldı.
- [ ] BigQuery service account yalnızca gerekli PO dataset okuma yetkisine sahip.
- [ ] `DOCKOS_PO_SOURCE=BIGQUERY`; ekranda pilot/mock PO kaynağı görünmüyor.
- [ ] SMTP hesabı, kurumsal gönderen adresi ve merkez depo alıcı listesi doğrulandı.
- [ ] SMTP domaini için SPF/DKIM/DMARC kontrolleri yapıldı.
- [ ] Tüm tedarikçi kullanıcı e-postaları Erişim Yönetimi ekranında eşleştirildi.
- [ ] `DOCKOS_STATE_FILE` kalıcı disk üzerindeki mutlak bir yola ayarlandı.
- [ ] Pilot JSON deposu nedeniyle backend tek worker ile çalışıyor (`DOCKOS_SINGLE_WORKER=true`).
- [ ] Harici yedek klasörü ve 30 günlük saklama tanımlandı.
- [ ] KVKK/veri saklama süresi ve audit erişim yetkisi onaylandı.

## Yayın kapısı

Backend başladıktan sonra:

```powershell
.\CHECK_DOCKOS_GO_LIVE.ps1 -ApiBase "https://dockos.example.com/api"
```

Komut tüm maddeleri `OK` göstermeden canlı trafik açılmamalıdır.

## Pilot sonrası zorunlu ölçekleme

Birden fazla backend worker veya sunucuya geçmeden önce JSON durum deposu PostgreSQL'e taşınmalıdır. RC7.5 tek-worker iç test/pilot sürümüdür.
