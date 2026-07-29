import React, { useRef, useState } from "react";
import { uploadSkuCatalog, loadSkuLibrary } from "../services/plonagramCatalogApi";
import "../styles/catalog-rule-engine.css";

export default function SkuUploadButton({ onUploaded, setStatus, setProducts, setSkuLibrary }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  async function handleFile(file) {
    if (!file) return;
    setUploading(true);
    setStatus?.("SKU catalog yükleniyor ve ürün kütüphanesine işleniyor...");

    try {
      const uploadResult = await uploadSkuCatalog(file, {
        allowAiDimensions: true,
        persistToMaster: true,
      });

      // Product Library'nin okuduğu gerçek kaynağı tekrar çekiyoruz.
      const libraryResult = await loadSkuLibrary({ limit: 10000 });
      const products = libraryResult.products || uploadResult.products || [];

      setSkuLibrary?.(products);
      setProducts?.(products);
      localStorage.setItem("plonagram.skuLibrary", JSON.stringify(products));
      localStorage.setItem("plonagram.lastSkuUpload", JSON.stringify({
        fileName: uploadResult.file_name,
        rowCount: uploadResult.row_count,
        storageSummary: uploadResult.storage_summary,
        fixtureSummary: uploadResult.fixture_summary,
        uploadedAt: new Date().toISOString(),
      }));

      setStatus?.(`SKU kütüphanesi güncellendi: ${products.length.toLocaleString("tr-TR")} ürün.`);
      onUploaded?.({ uploadResult, libraryResult, products });
    } catch (err) {
      console.error(err);
      setStatus?.(`SKU yükleme hatası: ${err.message}`);
      alert(`SKU yükleme hatası: ${err.message}`);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="sku-upload-inline">
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.txt"
        hidden
        onChange={(event) => handleFile(event.target.files?.[0])}
      />
      <button
        type="button"
        className="plona-primary-btn"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
      >
        {uploading ? "SKU işleniyor..." : "SKU Catalog Yükle"}
      </button>
      <span className="sku-upload-hint">Yükleme sonrası Product Library otomatik güncellenir.</span>
    </div>
  );
}
