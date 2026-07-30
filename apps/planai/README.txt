Bu paket 3 şeyi düzeltir:
1) 3D açılışı daha uzak/kuş bakışı başlar.
2) Layout editor arka plan yazıları/3D sahne sızdırmaz.
3) Layout editor içinde koridor bazlı modül sayısı ve modül yönü yönetilir.

Değiştirilecek dosyalar:
frontend/src/components/Depot3D.jsx
frontend/src/components/LayoutEditor.jsx
frontend/src/components/LayoutEditor.css

Önemli:
App.jsx içindeki handleLayoutChange payload'da module_count ve module_orientations alanlarını planograma merge etmezse, layout editor içinde görünür ama kalıcı olarak module üretmez.
