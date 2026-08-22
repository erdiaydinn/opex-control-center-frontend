"""DXF writer for measured Planogram CAD previews.

Kept separate from SVG rendering so DXF serialization can be tested and
hardened independently. This is an engineering preview, not installation or
production evidence.
"""

from __future__ import annotations

import io
from typing import Any

import ezdxf

import cad_drawing as cad

DXF_EXPORT_CONTRACT = "planogram-measured-dxf-preview-v1"


def build_dxf_preview(
    *,
    result: dict[str, Any] | None,
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
) -> dict[str, Any]:
    profile = cad._profile(store_dna)
    if not profile["available"]:
        return {
            "contract": DXF_EXPORT_CONTRACT,
            "available": False,
            "preview_only": True,
            "production_authority": False,
            "reason": profile["reason"],
        }

    schema_version = int(profile["schema_version"])
    layout_truth = cad._layout_truth(layout, store_dna, schema_version)
    if not layout_truth.get("valid"):
        return {
            "contract": DXF_EXPORT_CONTRACT,
            "available": False,
            "preview_only": True,
            "production_authority": False,
            "reason": "layout_architecture_invalid",
            "blockers": list(layout_truth.get("blockers") or []),
        }

    architecture = (store_dna or {})["architecture"]
    floor_width_m = cad._number(architecture.get("floor_width_m"))
    floor_depth_m = cad._number(architecture.get("floor_depth_m"))
    product_counts = cad._product_counts(result)

    architecture_rows: list[dict[str, Any]] = []
    for element in architecture.get("elements") or []:
        width = cad._number(element.get("width_m"))
        depth = cad._number(element.get("depth_m"))
        if width <= 0 or depth <= 0:
            continue
        points = cad._rectangle_points(
            element,
            width_m=width,
            depth_m=depth,
            schema_version=schema_version,
        )
        center = (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
        element_type = cad._text(element.get("element_type")).lower()
        architecture_rows.append(
            {
                "id": cad._text(element.get("element_id")),
                "label": cad._text(element.get("label")) or element_type,
                "layer": cad._architecture_layer(element_type),
                "center": center,
                "points": points,
            }
        )

    fixture_rows: list[dict[str, Any]] = []
    for aisle in (layout or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            width, depth = cad._module_dimensions(module)
            if width <= 0 or depth <= 0:
                continue
            points = cad._rectangle_points(
                module,
                width_m=width,
                depth_m=depth,
                schema_version=schema_version,
            )
            center = (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )
            key = cad._module_key(aisle, module)
            fixture_rows.append(
                {
                    "id": key,
                    "label": f"{key} · {product_counts.get(key, 0)} SKU",
                    "layer": cad.LAYER_FIXTURE,
                    "center": center,
                    "points": points,
                }
            )

    doc = ezdxf.new("R2010", setup=True)
    for layer in cad.DXF_LAYERS:
        if layer not in doc.layers:
            doc.layers.add(layer)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (floor_width_m, 0), (floor_width_m, floor_depth_m), (0, floor_depth_m)],
        close=True,
        dxfattribs={"layer": cad.LAYER_FLOOR},
    )

    for meter in range(1, int(floor_width_m) + 1):
        msp.add_line((meter, 0), (meter, floor_depth_m), dxfattribs={"layer": cad.LAYER_GRID})
    for meter in range(1, int(floor_depth_m) + 1):
        msp.add_line((0, meter), (floor_width_m, meter), dxfattribs={"layer": cad.LAYER_GRID})

    label_count = 0
    for row in architecture_rows + fixture_rows:
        msp.add_lwpolyline(row["points"], close=True, dxfattribs={"layer": row["layer"]})
        if label_count < cad.MAX_LABELS:
            entity = msp.add_text(
                row["label"],
                height=0.12,
                dxfattribs={"layer": cad.LAYER_LABEL},
            )
            entity.set_placement(row["center"])
            label_count += 1

    for route in cad._route_paths(result):
        points = [
            (cad._number(raw[0]), cad._number(raw[1]))
            for raw in route["path"]
            if isinstance(raw, (list, tuple)) and len(raw) >= 2
        ]
        if len(points) >= 2:
            msp.add_lwpolyline(points, dxfattribs={"layer": cad.LAYER_ROUTE})

    msp.add_line(
        (0, -0.4),
        (floor_width_m, -0.4),
        dxfattribs={"layer": cad.LAYER_DIMENSION},
    )
    width_text = msp.add_text(
        f"{floor_width_m:.2f} m",
        height=0.14,
        dxfattribs={"layer": cad.LAYER_DIMENSION},
    )
    width_text.set_placement((floor_width_m / 2.0, -0.32))
    msp.add_line(
        (-0.4, 0),
        (-0.4, floor_depth_m),
        dxfattribs={"layer": cad.LAYER_DIMENSION},
    )
    depth_text = msp.add_text(
        f"{floor_depth_m:.2f} m",
        height=0.14,
        dxfattribs={"layer": cad.LAYER_DIMENSION, "rotation": 90},
    )
    depth_text.set_placement((-0.32, floor_depth_m / 2.0))

    stream = io.StringIO()
    doc.write(stream)
    payload = stream.getvalue()
    return {
        "contract": DXF_EXPORT_CONTRACT,
        "available": True,
        "preview_only": True,
        "production_authority": False,
        "production_evidence": False,
        "installation_approved": False,
        "schema_version": schema_version,
        "layers": list(cad.DXF_LAYERS),
        "dxf": payload,
        "entity_counts": {
            "architecture": len(architecture_rows),
            "fixtures": len(fixture_rows),
            "routes": len(cad._route_paths(result)),
        },
    }
