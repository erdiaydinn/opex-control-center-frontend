const RAW_STAFFING_NORMS = `
Ali Sancaktar|Cemal Akçay|Bostancı (İstanbul)|16
Ali Sancaktar|Cemal Akçay|Şemsettin Günaltay (İstanbul)|12
Ali Sancaktar|Cemal Akçay|Lalezar (İstanbul)|11
Ali Sancaktar|Cemal Akçay|Kozyatağı (İstanbul)|9
Ali Sancaktar|Cemal Akçay|Göztepe (İstanbul)|16
Ali Sancaktar|Cemal Akçay|Taşköprü (İstanbul)|10
Ali Sancaktar|Cemal Akçay|Üsküdar (İstanbul)|12
Ali Sancaktar|Cemal Akçay|Anka (İstanbul)|28
Ali Sancaktar|Cemal Akçay|Anadolu Hisarı (İstanbul)|9
Ali Sancaktar|Özgür Albay|Pendik (İstanbul)|11
Ali Sancaktar|Özgür Albay|Kartal Cumhuriyet (İstanbul)|11
Ali Sancaktar|Özgür Albay|Osmangazi (İstanbul)|9
Ali Sancaktar|Özgür Albay|Kulaksız (İstanbul)|13
Ali Sancaktar|Özgür Albay|Tatlısu (İstanbul)|11
Ali Sancaktar|Özgür Albay|Sabiha Gökçen (İstanbul)|11
Ali Sancaktar|Özgür Albay|Çekmeköy (İstanbul)|11
Ali Sancaktar|Özgür Albay|Yeni Çamlıca (İstanbul)|8
Ali Sancaktar|Özgür Albay|Örnek (İstanbul)|11
Ali Sancaktar|Özgür Albay|Kısıklı (İstanbul)|9
Ali Sancaktar|Özgür Albay|Namık Kemal (İstanbul)|12
Ali Sancaktar|Özgür Albay|Şehit Turan (İstanbul)|10
Ali Sancaktar|Özhan Alpay|Fulya (İstanbul)|34
Ali Sancaktar|Özhan Alpay|Yıldırım (Bursa)|10
Ali Sancaktar|Özhan Alpay|Çekirge (Bursa)|8
Ali Sancaktar|Özhan Alpay|İsmetpaşa (Çanakkale)|9
Ali Sancaktar|Özhan Alpay|Yalova Merkez (Yalova)|9
Ali Sancaktar|Özhan Alpay|Gebze (Kocaeli)|9
Ali Sancaktar|Özhan Alpay|Akpınar (Bursa)|9
Ali Sancaktar|Özhan Alpay|Görükle (Bursa)|12
Ali Sancaktar|Özhan Alpay|Bandırma (Balıkesir)|9
Ali Sancaktar|Özhan Alpay|Serdivan (Sakarya)|13
Ali Sancaktar|Özhan Alpay|Çeliktepe (İstanbul)|11
Anıl Kırıcı|Bekir Korkmaz|Çukurambar (Ankara)|10
Anıl Kırıcı|Bekir Korkmaz|Esat (Ankara)|12
Anıl Kırıcı|Bekir Korkmaz|Bahçelievler (Ankara)|13
Anıl Kırıcı|Bekir Korkmaz|Cebeci (Ankara)|11
Anıl Kırıcı|Bekir Korkmaz|Bolu Merkez (Bolu)|8
Anıl Kırıcı|Bekir Korkmaz|Dikmen (Ankara)|10
Anıl Kırıcı|Bekir Korkmaz|Körpeşler (Düzce)|8
Anıl Kırıcı|Bekir Korkmaz|Turan Güneş (Ankara)|11
Anıl Kırıcı|Bekir Korkmaz|Dicle (Diyarbakır)|7
Anıl Kırıcı|Hasan Koca|Bilkent (Ankara)|10
Anıl Kırıcı|Hasan Koca|Tepebaşı (Eskişehir)|12
Anıl Kırıcı|Hasan Koca|Alacaatli (Ankara)|9
Anıl Kırıcı|Hasan Koca|Melikgazi (Kayseri)|10
Anıl Kırıcı|Hasan Koca|Şeref (Ankara)|11
Anıl Kırıcı|Hasan Koca|Eryaman (Ankara)|11
Anıl Kırıcı|Hasan Koca|Batıkent (Ankara)|9
Anıl Kırıcı|Hasan Koca|Keçiören (Ankara)|13
Anıl Kırıcı|Hasan Koca|Etimesgut (Ankara)|9
Anıl Kırıcı|Hasan Koca|Atakum (Samsun)|10
Anıl Kırıcı|Kazım Özgün Şencan|Gümbet (Muğla)|8
Anıl Kırıcı|Kazım Özgün Şencan|Ege Üniversitesi (İzmir)|12
Anıl Kırıcı|Kazım Özgün Şencan|İmbatlı (İzmir)|19
Anıl Kırıcı|Kazım Özgün Şencan|Alsancak (İzmir)|11
Anıl Kırıcı|Kazım Özgün Şencan|Pamukkale (Denizli)|14
Anıl Kırıcı|Kazım Özgün Şencan|Bornova (İzmir)|12
Anıl Kırıcı|Kazım Özgün Şencan|Gaziemir (İzmir)|7
Anıl Kırıcı|Onur Kadıoğlu|Buca (İzmir)|21
Anıl Kırıcı|Onur Kadıoğlu|Çiğli (İzmir)|15
Anıl Kırıcı|Onur Kadıoğlu|Kuşadası (Aydın)|8
Anıl Kırıcı|Onur Kadıoğlu|Balçova (İzmir)|10
Anıl Kırıcı|Onur Kadıoğlu|Menteşe (Muğla)|8
Anıl Kırıcı|Özgür Topuz|Lara (Antalya)|14
Anıl Kırıcı|Özgür Topuz|Beyhekim (Konya)|9
Anıl Kırıcı|Özgür Topuz|Muratpaşa (Antalya)|14
Anıl Kırıcı|Özgür Topuz|Seyhan (Adana)|15
Anıl Kırıcı|Özgür Topuz|Yenişehir (Mersin)|18
Anıl Kırıcı|Özgür Topuz|Çukurova (Adana)|14
Anıl Kırıcı|Özgür Topuz|Gülistan (Isparta)|10
Anıl Kırıcı|Özgür Topuz|Alanya (Antalya)|11
Anıl Kırıcı|Özgür Topuz|Konyaaltı (Antalya)|12
Anıl Kırıcı|Özgür Topuz|Selçuklu (Konya)|11
Engin Gökkaya|Ali Karakuz|Zümrütevler (İstanbul)|11
Engin Gökkaya|Ali Karakuz|Ortaköy (İstanbul)|10
Engin Gökkaya|Ali Karakuz|Karlıktepe (İstanbul)|14
Engin Gökkaya|Ali Karakuz|Maltepe (İstanbul)|11
Engin Gökkaya|Ali Karakuz|Ayazağa (İstanbul)|13
Engin Gökkaya|Ali Karakuz|Alibeyköy (İstanbul)|13
Engin Gökkaya|Ali Karakuz|Eyüp Çırçır (İstanbul)|14
Engin Gökkaya|Ali Karakuz|İçerenköy (İstanbul)|12
Engin Gökkaya|Ali Karakuz|Tuzla (İstanbul)|8
Engin Gökkaya|Selçuk Çetin|Tuğba (İstanbul)|9
Engin Gökkaya|Selçuk Çetin|Bayrampaşa (İstanbul)|12
Engin Gökkaya|Selçuk Çetin|Ferahevler (İstanbul)|9
Engin Gökkaya|Selçuk Çetin|Maden (İstanbul)|8
Engin Gökkaya|Selçuk Çetin|Etiler (İstanbul)|9
Engin Gökkaya|Selçuk Çetin|Göktürk (İstanbul)|9
Engin Gökkaya|Selçuk Çetin|Bağcılar Sancak (İstanbul)|11
Engin Gökkaya|Selim Keşçi|Bahçeşehir 2. Kısım (İstanbul)|17
Engin Gökkaya|Selim Keşçi|Süleymanpaşa (Tekirdağ)|9
Engin Gökkaya|Selim Keşçi|Şükrüpaşa (Edirne)|15
Engin Gökkaya|Selim Keşçi|Avcılar (İstanbul)|11
Engin Gökkaya|Selim Keşçi|Kavaklı (İstanbul)|16
Engin Gökkaya|Selim Keşçi|Yenikent (İstanbul)|20
Engin Gökkaya|Selim Keşçi|Odak (İstanbul)|9
Engin Gökkaya|Selim Keşçi|Başakşehir (İstanbul)|9
Engin Gökkaya|Ufuk Altun|Fatih (İstanbul)|12
Engin Gökkaya|Ufuk Altun|Ötüken (İstanbul)|21
Engin Gökkaya|Ufuk Altun|Çerkezköy (Tekirdağ)|9
Engin Gökkaya|Ufuk Altun|Çorlu (Tekirdağ)|10
Engin Gökkaya|Ufuk Altun|Mimaroba (İstanbul)|8
Engin Gökkaya|Ufuk Altun|Zeytinburnu (İstanbul)|9
`;

export const DEFAULT_STAFFING_NORMS = RAW_STAFFING_NORMS.trim().split("\n").map((line, index) => {
  const [regionalManager, regionalExecutive, warehouse, norm] = line.split("|");
  return { id: `NORM-${String(index + 1).padStart(3, "0")}`, regionalManager, regionalExecutive, warehouse, norm: Number(norm), active: true };
});

const NAME_ALIASES = new Map([
  ["anka (istanbul)", "Anka (İstanbul)"],
  ["alacaatlı (ankara)", "Alacaatli (Ankara)"],
  ["lalezar (bağdat caddesi)", "Lalezar (İstanbul)"],
  ["kadıköy taşköprü", "Taşköprü (İstanbul)"],
  ["maltepe üst", "Zümrütevler (İstanbul)"],
  ["bahçelievler (anıttepe)", "Bahçelievler (Ankara)"],
  ["nene hatun (esat)", "Esat (Ankara)"],
  ["denizli", "Pamukkale (Denizli)"],
  ["şeref (ankara)", "Şeref (Ankara)"],
]);

export const HR_WAREHOUSE_CODE_MAP = new Map([
  ["200", "Bostancı (İstanbul)"], ["281", "Göztepe (İstanbul)"], ["71", "Kozyatağı (İstanbul)"], ["198", "Lalezar (İstanbul)"],
  ["164", "Şemsettin Günaltay (İstanbul)"], ["18", "Taşköprü (İstanbul)"], ["280", "Üsküdar (İstanbul)"], ["81", "Anadolu Hisarı (İstanbul)"],
  ["283", "Anka (İstanbul)"], ["46", "Çekmeköy (İstanbul)"], ["92", "Kartal Cumhuriyet (İstanbul)"], ["180", "Kısıklı (İstanbul)"],
  ["86", "Namık Kemal (İstanbul)"], ["94", "Osmangazi (İstanbul)"], ["32", "Örnek (İstanbul)"], ["265", "Pendik (İstanbul)"],
  ["185", "Şehit Turan (İstanbul)"], ["159", "Tatlısu (İstanbul)"], ["96", "Yeni Çamlıca (İstanbul)"], ["206", "Kulaksız (İstanbul)"],
  ["288", "Sabiha Gökçen (İstanbul)"], ["133", "Akpınar (Bursa)"], ["173", "Bandırma (Balıkesir)"], ["134", "Çekirge (Bursa)"],
  ["287", "Fulya (İstanbul)"], ["39", "Görükle (Bursa)"], ["99", "İsmetpaşa (Çanakkale)"], ["124", "Serdivan (Sakarya)"],
  ["194", "Yalova Merkez (Yalova)"], ["172", "Yıldırım (Bursa)"], ["246", "Çeliktepe (İstanbul)"], ["125", "Gebze (Kocaeli)"],
  ["51", "Bahçelievler (Ankara)"], ["138", "Bolu Merkez (Bolu)"], ["267", "Cebeci (Ankara)"], ["29", "Çukurambar (Ankara)"],
  ["284", "Dicle (Diyarbakır)"], ["58", "Dikmen (Ankara)"], ["272", "Esat (Ankara)"], ["195", "Körpeşler (Düzce)"],
  ["48", "Turan Güneş (Ankara)"], ["239", "Alacaatli (Ankara)"], ["167", "Atakum (Samsun)"], ["62", "Batıkent (Ankara)"],
  ["223", "Bilkent (Ankara)"], ["57", "Eryaman (Ankara)"], ["116", "Etimesgut (Ankara)"], ["277", "Keçiören (Ankara)"],
  ["141", "Melikgazi (Kayseri)"], ["273", "Şeref (Ankara)"], ["275", "Tepebaşı (Eskişehir)"], ["23", "Alsancak (İzmir)"],
  ["24", "Bornova (İzmir)"], ["187", "Ege Üniversitesi (İzmir)"], ["113", "Gaziemir (İzmir)"], ["219", "Gümbet (Muğla)"],
  ["266", "İmbatlı (İzmir)"], ["66", "Pamukkale (Denizli)"], ["43", "Balçova (İzmir)"], ["22", "Buca (İzmir)"],
  ["158", "Çiğli (İzmir)"], ["220", "Kuşadası (Aydın)"], ["176", "Menteşe (Muğla)"], ["165", "Alanya (Antalya)"],
  ["147", "Beyhekim (Konya)"], ["111", "Çukurova (Adana)"], ["67", "Gülistan (Isparta)"], ["274", "Konyaaltı (Antalya)"],
  ["119", "Lara (Antalya)"], ["73", "Muratpaşa (Antalya)"], ["139", "Selçuklu (Konya)"], ["110", "Seyhan (Adana)"],
  ["98", "Yenişehir (Mersin)"], ["169", "Ayazağa (İstanbul)"], ["78", "Eyüp Çırçır (İstanbul)"], ["34", "İçerenköy (İstanbul)"],
  ["161", "Karlıktepe (İstanbul)"], ["189", "Maltepe (İstanbul)"], ["278", "Ortaköy (İstanbul)"], ["82", "Tuzla (İstanbul)"],
  ["77", "Zümrütevler (İstanbul)"], ["80", "Alibeyköy (İstanbul)"], ["128", "Göktürk (İstanbul)"], ["83", "Bayrampaşa (İstanbul)"],
  ["171", "Etiler (İstanbul)"], ["122", "Ferahevler (İstanbul)"], ["107", "Maden (İstanbul)"], ["245", "Tuğba (İstanbul)"],
  ["84", "Bağcılar Sancak (İstanbul)"], ["38", "Avcılar (İstanbul)"], ["117", "Bahçeşehir 2. Kısım (İstanbul)"], ["286", "Başakşehir (İstanbul)"],
  ["95", "Kavaklı (İstanbul)"], ["285", "Odak (İstanbul)"], ["205", "Süleymanpaşa (Tekirdağ)"], ["70", "Şükrüpaşa (Edirne)"],
  ["85", "Yenikent (İstanbul)"], ["204", "Çerkezköy (Tekirdağ)"], ["142", "Çorlu (Tekirdağ)"], ["53", "Fatih (İstanbul)"],
  ["102", "Mimaroba (İstanbul)"], ["282", "Ötüken (İstanbul)"], ["93", "Zeytinburnu (İstanbul)"],
]);

export function normalizeWarehouseName(value = "") {
  const cleaned = String(value).replace(/^Yemeksepeti Market,\s*/i, "").trim();
  return NAME_ALIASES.get(cleaned.toLocaleLowerCase("tr-TR")) || cleaned.replace("(istanbul)", "(İstanbul)");
}

export function resolveHrWarehouse(value = "", explicitCode = "") {
  const raw = String(value || "").trim();
  const codeText = String(explicitCode || "").trim();
  const code = (codeText.match(/\d+/)?.[0] || raw.match(/^\s*(\d+)\s*-/)?.[1] || (/^\d+$/.test(raw) ? raw : "")).replace(/^0+/, "");
  const mapped = HR_WAREHOUSE_CODE_MAP.get(code);
  const nameWithoutCode = raw.replace(/^\s*\d+\s*-\s*/, "");
  return { warehouseCode: code, warehouse: mapped || normalizeWarehouseName(nameWithoutCode || raw) };
}
