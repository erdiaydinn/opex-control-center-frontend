def find_product(planogram, query):
    query = str(query).lower()

    for a in planogram["aisles"]:
        for m in a["modules"]:
            for s in m["shelves"]:
                for p in s["products"]:

                    if query in str(p.get("sku", "")).lower() \
                    or query in str(p.get("product_name", "")).lower():

                        return {
                            "sku": p["sku"],
                            "location": {
                                "aisle": a["aisle_id"],
                                "module": m["module_id"],
                                "shelf": s["shelf_no"]
                            }
                        }

    return {"found": False}