# PLONAGRAM Pascal Full Editor Bridge V1

Bu paket iki şeyi düzeltir:

1. Loading/soldaki logo tekrar mimari P monogram çizgisine döner. Eski kırık sembol kalkar.
2. Mimari Düzenleyici, Pascal editor reposunu tam ekran micro-frontend olarak kullanacak şekilde bridge ekranına dönüşür.

## Neden iframe/micro-frontend?
Pascal editor repo Next.js + React 19 + @react-three/fiber 9 stack'iyle geliyor. PLONAGRAM frontend şu anda Vite + React 18. Bu iki dünyayı aynı src içine doğrudan gömmek dependency ağacını kırar. Doğru entegrasyon: Pascal ayrı çalışır, PLONAGRAM onu iframe/micro-frontend olarak açar ve postMessage bridge ile layout state senkronlanır.

## Pascal editor çalıştırma
Ayrı terminalde:

```bat
cd C:\Users\ErdiAydın\planai\editor-main
bun install
bun run dev
```

Varsayılan URL: http://localhost:3002

PLONAGRAM içindeki Mimari Düzenleyici ekranında bu URL alanına yazılır.

## Admin obje promptu
Mimari Düzenleyici içindeki prompt alanına örnek:

- 2m Algida dolap ekle
- Donuk oda ekle
- Soğuk oda +4 ekle
- Dispatch alanı ekle
- D koridoruna raf modülü ekle

Bu şimdilik PLONAGRAM layout state'ine obje ekler ve Pascal iframe'ine `AI_CREATE_OBJECT` mesajı yollar. Pascal repo içine küçük bir listener eklersek çift yönlü gerçek senkron tamamlanır.
