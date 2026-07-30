
from fastapi import APIRouter, HTTPException, Query
import unicodedata
from engine import enrich_product, load_master

router = APIRouter(prefix="/master-products", tags=["master-products"])


def _public_product(product):
    """Keep supplier contacts and purchasing identities out of API responses."""
    private_tokens = (
        "iletisim", "telefon", "mail", "email", "siparis yetkilisi",
        "satin alma", "satin_alma", "satinalma", "contact",
    )
    public = {}
    for field, value in product.items():
        folded = unicodedata.normalize("NFKD", str(field).casefold())
        folded = folded.encode("ascii", "ignore").decode("ascii")
        if any(token in folded for token in private_tokens):
            continue
        public[field] = value
    return public


def load_products():
    master = load_master()
    if not master.get("source_path"):
        raise HTTPException(status_code=404, detail="master_products.csv veya catalog.csv bulunamadı")
    return [_public_product(enrich_product(row, allow_ai_dimensions=False)) for row in master.get("rows", [])]

@router.get("")
def list_products(limit: int = Query(200, ge=1, le=10000), offset: int = Query(0, ge=0)):
    rows = load_products()
    return {"total": len(rows), "limit": limit, "offset": offset, "products": rows[offset:offset+limit]}

@router.get("/search")
def search_products(q: str = "", storage: str = "", limit: int = Query(80, ge=1, le=500)):
    rows = load_products()
    ql = q.lower().strip()
    st = storage.upper().strip()
    def ok(r):
        hay = f"{r.get('sku','')} {r.get('product_name','')} {r.get('brand','')} {r.get('category_l1','')} {r.get('category_l2','')}".lower()
        return (not ql or ql in hay) and (not st or str(r.get("storage_type","")).upper().startswith(st))
    return {"products": [r for r in rows if ok(r)][:limit]}

@router.get("/{sku}")
def get_product(sku: str):
    for r in load_products():
        if str(r.get("sku")) == str(sku):
            return r
    raise HTTPException(status_code=404, detail="SKU bulunamadı")
