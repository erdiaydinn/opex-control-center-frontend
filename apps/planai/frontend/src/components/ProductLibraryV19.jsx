import React, { useEffect, useMemo, useState } from "react";
import { fetchProductLibrary, uploadProductsCsv } from "../services/plonagramV19Api";
import { t19 } from "../i18n/plonagramV19Dictionary";
import "../styles/plonagram-v19.css";

function normalizeProduct(row = {}) {
  const width = row.width_cm ?? row.product_width_in_cm ?? "";
  const depth = row.depth_cm ?? row.product_length_in_cm ?? "";
  const height = row.height_cm ?? row.product_height_in_cm ?? "";
  return {
    raw: row,
    sku: row.sku || row.SKU || row.barcode || "",
    barcode: row.barcode || row.product_barcodes || "",
    name: row.product_name || row.product_name_local || row.name || "İsimsiz ürün",
    brand: row.brand || row.brand_name || "-",
    category: row.category_l1 || row.frontend_category_local || row.category || "-",
    subcategory: row.category_l2 || row.frontend_subcategory_local || row.subcategory || "-",
    storage: row.storage_type || row.storage || "-",
    storageRaw: row.storage_raw || "-",
    width,
    depth,
    height,
    casePack: row.case_pack_qty || row.case_pack || "-",
    image: row.image_url || row.catalog_image_url || row.pim_image_url || "",
    confidence: row.placement_confidence || row.product_confidence || null,
  };
}

function ProductImage({ product }) {
  if (!product.image) {
    return <div className="v19-product-img v19-product-img-empty">SKU</div>;
  }
  return <img className="v19-product-img" src={product.image} alt={product.name} loading="lazy" />;
}

export default function ProductLibraryV19({ lang = "tr", onProductsLoaded }) {
  const [query, setQuery] = useState("");
  const [storage, setStorage] = useState("");
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [lastUpload, setLastUpload] = useState(null);

  async function loadProducts(next = {}) {
    setLoading(true);
    setError("");
    try {
      const data = await fetchProductLibrary({ q: next.q ?? query, storage: next.storage ?? storage, limit: 500 });
      const rows = data.products || data.rows || [];
      const normalized = rows.map(normalizeProduct);
      setProducts(normalized);
      onProductsLoaded?.(rows);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProducts({ q: "", storage: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const result = await uploadProductsCsv(file, true);
      setLastUpload(result);
      await loadProducts({ q: "", storage });
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  function handleSearchKeyDown(event) {
    if (event.key === "Enter") {
      loadProducts({ q: query, storage });
    }
  }

  const stats = useMemo(() => {
    const total = products.length;
    const byStorage = products.reduce((acc, p) => {
      const key = String(p.storage || "UNKNOWN").toUpperCase();
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    return { total, byStorage };
  }, [products]);

  return (
    <section className="v19-page" dir={lang === "ar" ? "rtl" : "ltr"}>
      <div className="v19-page-head">
        <div>
          <div className="v19-eyebrow">DATA CENTER</div>
          <h1>{t19(lang, "productLibrary")}</h1>
          <p>{t19(lang, "noMock")}</p>
        </div>
        <label className="v19-upload-button">
          <input type="file" accept=".csv,.xlsx" onChange={handleUpload} />
          {uploading ? `${t19(lang, "loading")}...` : t19(lang, "uploadSku")}
        </label>
      </div>

      <div className="v19-toolbar">
        <input
          className="v19-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          placeholder={t19(lang, "searchPlaceholder")}
        />
        <select className="v19-select" value={storage} onChange={(e) => { setStorage(e.target.value); loadProducts({ storage: e.target.value }); }}>
          <option value="">Tümü</option>
          <option value="AMBIENT">AMBIENT</option>
          <option value="CHILLED">CHILLED</option>
          <option value="FROZEN">FROZEN</option>
        </select>
        <button className="v19-secondary" onClick={() => loadProducts({ q: query, storage })}>Ara</button>
        <span className="v19-help">{t19(lang, "pressEnter")}</span>
      </div>

      {error && <div className="v19-alert v19-alert-danger">{t19(lang, "error")}: {error}</div>}
      {lastUpload && <div className="v19-alert v19-alert-success">Upload tamamlandı. Satır: {lastUpload.row_count || lastUpload.saved_rows || "?"}</div>}

      <div className="v19-kpi-grid">
        <div className="v19-kpi"><span>Toplam</span><b>{stats.total}</b></div>
        <div className="v19-kpi"><span>AMBIENT</span><b>{stats.byStorage.AMBIENT || 0}</b></div>
        <div className="v19-kpi"><span>CHILLED</span><b>{stats.byStorage.CHILLED || 0}</b></div>
        <div className="v19-kpi"><span>FROZEN</span><b>{stats.byStorage.FROZEN || 0}</b></div>
      </div>

      <div className="v19-card">
        <div className="v19-card-head">
          <h3>{products.length} {t19(lang, "productsFound")}</h3>
          {loading && <span className="v19-pill">{t19(lang, "loading")}</span>}
        </div>
        <div className="v19-table-wrap">
          <table className="v19-table">
            <thead>
              <tr>
                <th>Görsel</th>
                <th>SKU</th>
                <th>Ürün</th>
                <th>{t19(lang, "brand")}</th>
                <th>{t19(lang, "category")}</th>
                <th>{t19(lang, "storage")}</th>
                <th>storage_raw</th>
                <th>{t19(lang, "dimensions")}</th>
                <th>{t19(lang, "casePack")}</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={`${p.sku}-${p.barcode}`}>
                  <td><ProductImage product={p} /></td>
                  <td><b>{p.sku}</b><br /><small>{p.barcode}</small></td>
                  <td>{p.name}</td>
                  <td>{p.brand}</td>
                  <td>{p.category}<br /><small>{p.subcategory}</small></td>
                  <td><span className={`v19-badge v19-${String(p.storage).toLowerCase()}`}>{p.storage}</span></td>
                  <td>{p.storageRaw}</td>
                  <td>{p.width}×{p.depth}×{p.height}</td>
                  <td>{p.casePack}</td>
                </tr>
              ))}
              {!loading && products.length === 0 && (
                <tr><td colSpan="9" className="v19-empty">Ürün bulunamadı. Arama kriterini değiştir veya CSV yükle.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
