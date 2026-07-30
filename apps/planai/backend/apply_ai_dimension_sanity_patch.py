
from pathlib import Path

MAIN = Path("main.py")
IMPORT_LINE = "from routers.ai_dimension_sanity import router as ai_dimension_sanity_router"
INCLUDE_LINE = "app.include_router(ai_dimension_sanity_router)"

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
print("main.py AI dimension sanity router ile güncellendi.")
