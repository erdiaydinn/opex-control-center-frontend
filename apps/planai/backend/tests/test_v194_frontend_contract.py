from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT

def assert_exists(rel):
    p = PKG / rel
    assert p.exists(), f"Missing {rel}"

if __name__ == "__main__":
    # This test is intended to be run from the unpacked patch folder before copy,
    # or adapted after copy. It validates that the frontend wiring files exist.
    base = Path(__file__).resolve().parents[2]
    required = [
        "frontend/src/services/plonagramV194Api.js",
        "frontend/src/components/DataPipeline/ABCUploadPanelV194.jsx",
        "frontend/src/components/Live3D/ProductTile3DV194.jsx",
        "frontend/src/components/Live3D/ShelfProductTilesV194.jsx",
    ]
    for rel in required:
        assert (base / rel).exists(), f"Missing {rel}"
    print("✅ V1.9.4 frontend wiring contract files exist")
