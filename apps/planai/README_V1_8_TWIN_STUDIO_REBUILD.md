# PLONAGRAM OS V1.8 — Twin Studio Rebuild

**Physics-True · Product-Rendered · OPEX-Bridge-Safe**

Bu paket yama değil, V1.8 için kontrollü rebuild temelidir. Hedef: 3D sahnede ürün adlarını label olarak yazmak yerine ürünleri rafların içine image tile / package block olarak render etmek; storage mismatch'i engine seviyesinde sıfır toleransla reddetmek; OPEX `/planogram` bridge'i blank screen yerine kontrollü health/error state ile yönetmek.

## Çözdüğü ana blocker'lar

- Storage mismatch: hard reject.
- Algida / Martek / özel fixture: ayrı fixture type.
- Blank scene: `TwinFallback2D` ve bridge health state.
- Ürün label kalabalığı: `ProductTile3D` image texture / fallback package block.
- Seç / taşı / düzenle: Layout Architect temel state contract.
- 5173/planogram: bridge component + retry/error state.

## Kurulum

### PlanAI frontend
```powershell
robocopy .\frontend C:\Users\ErdiAydın\planai\frontend /E /XD node_modules dist
cd C:\Users\ErdiAydın\planai\frontend
npm install three @react-three/fiber @react-three/drei
npm run dev -- --host 0.0.0.0 --port 5174
```

### PlanAI backend
```powershell
robocopy .\backend C:\Users\ErdiAydın\planai\backend /E /XD database __pycache__ /XF *.pyc
cd C:\Users\ErdiAydın\planai\backend
python -m pytest tests/test_v18_physics_scene.py
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

### OPEX bridge
```powershell
robocopy .\opex\frontend C:\Users\ErdiAydın\opex-control-center-scaffold\frontend /E /XD node_modules dist
cd C:\Users\ErdiAydın\opex-control-center-scaffold\frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

## Done means done

- `localhost:5174` açılır.
- `localhost:5173/planogram` içinde iframe açılır.
- 5174 kapalıyken blank screen değil bridge error state görünür.
- 3D ürünler yazı label değil tile/block olarak görünür.
- Algida ambient'e düşmez.
- +4 ürün -18'e düşmez.
- -18 ürün +4'e düşmez.
- 100 cm raf / 20 cm ürün max 5 facing.
