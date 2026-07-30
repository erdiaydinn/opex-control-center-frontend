KURULUM
1) Bu iki dosyayı frontend/src/components/auth/ altına koy:
   - PlonagramOperationHero.jsx
   - PlonagramOperationHero.css

2) PlonagramAuth.jsx içinde import et:
   import PlonagramOperationHero from "./PlonagramOperationHero";

3) Login ekranındaki eski statik sketch/image alanını bununla değiştir:
   <PlonagramOperationHero />

4) npm run dev

Not: Ek paket gerekmez. Sadece React + CSS animasyon kullanır.
