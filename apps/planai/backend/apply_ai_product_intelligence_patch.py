
from pathlib import Path

MAIN = Path("main.py")
IMPORT_LINE = "from routers.ai_product_intelligence import router as ai_product_intelligence_router"
INCLUDE_LINE = "app.include_router(ai_product_intelligence_router)"

text = MAIN.read_text(encoding="utf-8")

if IMPORT_LINE not in text:
    anchor = "from engine import ("
    if anchor in text:
        text = text.replace(anchor, IMPORT_LINE + "\n\n" + anchor)
    else:
        text = IMPORT_LINE + "\n" + text

if INCLUDE_LINE not in text:
    marker = 'app = FastAPI(title="Plonagram Premium Backend")'
    if marker in text:
        text = text.replace(marker, marker + "\n\n" + INCLUDE_LINE)
    else:
        raise SystemExit("app = FastAPI(...) satırı bulunamadı.")

MAIN.write_text(text, encoding="utf-8")
print("main.py AI product intelligence router ile güncellendi.")
