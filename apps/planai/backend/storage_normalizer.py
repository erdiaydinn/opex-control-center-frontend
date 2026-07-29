
from typing import Any, Dict

TR_MAP = str.maketrans({"ı":"i","İ":"i","ğ":"g","Ğ":"g","ü":"u","Ü":"u","ş":"s","Ş":"s","ö":"o","Ö":"o","ç":"c","Ç":"c"})

def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()

def norm(v: Any) -> str:
    return _s(v).translate(TR_MAP).lower().strip()

def product_text(row: Dict[str, Any]) -> str:
    keys = [
        "sku","barcode","product_barcodes","product_name","product_name_local","product_name_english",
        "brand","brand_name","brand_owner_name_local","category_l1","category_l2",
        "frontend_category_local","frontend_subcategory_local","frontend_category","frontend_subcategory",
        "pim_cat_l1","pim_cat_l2","pim_cat_l3","pim_cat_l4","storage_type","Storage Type","Storage"
    ]
    return norm(" ".join(_s(row.get(k)) for k in keys))

def normalize_storage_type(row_or_text: Any) -> str:
    if isinstance(row_or_text, dict):
        text = product_text(row_or_text)
        raw = norm(row_or_text.get("storage_type") or row_or_text.get("Storage Type") or row_or_text.get("Storage"))
    else:
        text = norm(row_or_text)
        raw = text

    ambient_terms = [
        "maden suyu","mineral water","soda","beypazari","beypazarı","sparkling water","gazoz","tonic",
        "su ","water","ice tea","icetea","meyve suyu","juice","kola","cola","fanta","sprite",
        "enerji icecegi","enerji içeceği","energy drink","cips","chips","lays","ruffles","doritos",
        "cikolata","çikolata","chocolate","gofret","biskuvi","bisküvi","kraker","bar","protein bar",
        "deterjan","temizlik","cleaner","domestos","sampuan","şampuan","sabun","bebek","baby",
        "pet","kedi","kopek","köpek","uht","uzun omurlu","uzun ömürlü","ekmek","bread",
        "mandalina","limon","portakal","patates","sogan","soğan","muz","domates","elma","armut","karpuz","kavun"
    ]
    frozen_terms = ["ice cream","dondurma","frozen","donuk","-18","algida","la lorraine","milfoy","milföy","donmus","donmuş"]
    chilled_terms = [
        "chilled","+4","soguk","soğuk","fridge","refrigerated","yogurt","yoğurt","ayran",
        "peynir","cheese","tereyagi","tereyağı","tavuk","chicken","et ","meat","balik","balık",
        "fish","sucuk","salam","sosis","deli","marul","maydanoz","roka","dereotu","nane","yesillik","yeşillik"
    ]

    if any(t in text for t in ambient_terms) and not any(t in text for t in frozen_terms):
        return "AMBIENT"
    if any(t in text for t in frozen_terms):
        return "FROZEN"
    if any(t in text for t in chilled_terms):
        return "CHILLED"
    if raw.startswith("frozen"):
        return "FROZEN"
    if raw.startswith("chilled"):
        return "CHILLED"
    return "AMBIENT"
