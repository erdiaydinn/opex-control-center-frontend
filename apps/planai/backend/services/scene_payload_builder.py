def build_scene_payload(planogram):
    fixtures = []
    products = []
    for aisle in planogram.get("aisles", []):
        for module in aisle.get("modules", []):
            fixture_id = f"{aisle.get('aisle_id')}-{module.get('module_id')}"
            shelves = []
            for shelf in module.get("shelves", []):
                shelf_id = f"{fixture_id}-S{shelf.get('shelf_no')}"
                shelf_products = []
                for p in shelf.get("products", []):
                    item = {
                        "sku": p.get("sku"),
                        "product_name": p.get("product_name"),
                        "image_url": p.get("image_url"),
                        "facing_count": p.get("facing_count") or p.get("facing") or 1,
                        "storage_type": p.get("storage_type"),
                        "merch_group": p.get("merch_group"),
                    }
                    shelf_products.append(item)
                    products.append({**item, "fixture_id": fixture_id, "shelf_id": shelf_id})
                shelves.append({
                    "shelf_id": shelf_id,
                    "shelf_no": shelf.get("shelf_no"),
                    "storage_class": shelf.get("allowed_storage_type"),
                    "width_cm": shelf.get("shelf_width_cm"),
                    "depth_cm": shelf.get("shelf_depth_cm"),
                    "height_cm": shelf.get("shelf_height_cm"),
                    "products": shelf_products,
                })
            fixtures.append({
                "fixture_id": fixture_id,
                "aisle_id": aisle.get("aisle_id"),
                "module_id": module.get("module_id"),
                "fixture_type": module.get("fixture_type") or module.get("module_type"),
                "storage_class": module.get("storage_class") or (shelves[0].get("storage_class") if shelves else "AMBIENT"),
                "width_cm": module.get("module_width_cm"),
                "depth_cm": module.get("module_depth_cm"),
                "height_cm": module.get("module_height_cm"),
                "shelves": shelves,
            })
    return {"store_code": planogram.get("store_code"), "fixtures": fixtures, "products": products, "layout_objects": planogram.get("layout_objects", []), "summary": {"fixture_count": len(fixtures), "product_tile_count": len(products)}}
