from pathlib import Path
import shutil
from datetime import datetime


def backup(path: Path, tag: str):
    if not path.exists():
        return None
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = path.with_suffix(path.suffix + f'.bak_{tag}_{stamp}')
    shutil.copyfile(path, dst)
    return dst


def patch_engine():
    p = Path('engine.py')
    if not p.exists():
        print('UYARI: engine.py bulunamadı. Bu script backend klasöründe çalıştırılmalı.')
        return False
    text = p.read_text(encoding='utf-8')
    original = text

    # Fulya gibi büyük layoutlarda sadece ilk 40 raf adayına bakmak kapasiteyi öldürür.
    text = text.replace(
        "    )[:40]\n\n    best = None",
        "    )\n\n    best = None"
    )
    text = text.replace(
        ")[:40]\n\n    best = None",
        ")\n\n    best = None"
    )

    if text != original:
        backup(p, 'fulya_full_candidate_scan')
        p.write_text(text, encoding='utf-8')
        print('engine.py güncellendi: shelf candidate [:40] limiti kaldırıldı.')
        return True

    print('engine.py içinde [:40] candidate limiti bulunamadı veya zaten kaldırılmış.')
    return False


def patch_main_lite_warning():
    p = Path('main.py')
    if not p.exists():
        print('UYARI: main.py bulunamadı.')
        return False
    text = p.read_text(encoding='utf-8')
    if 'products = products[:500]' in text:
        print('NOT: main.py içinde /generate-planogram-lite hâlâ max 500 SKU ile çalışıyor. Frontend artık full /generate-planogram çağırıyor; lite endpoint test için kalabilir.')
    return True


if __name__ == '__main__':
    print('PLONAGRAM Fulya full generation hotfix uygulanıyor...')
    patch_engine()
    patch_main_lite_warning()
    print('Tamamlandı. Backend restart et: python -m uvicorn main:app --host 127.0.0.1 --port 8001')
