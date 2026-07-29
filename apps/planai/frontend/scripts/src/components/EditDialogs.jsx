import React, { useEffect, useMemo, useState } from "react";
import { RULES } from "../utils/planogram";

export function SizeDialog({ target, onClose, onSave }) {
  const [form, setForm] = useState({});
  useEffect(() => { setForm(target?.values || {}); }, [target]);
  if (!target) return null;
  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }
  return (
    <div className="pe-modal-backdrop"><div className="pe-dialog">
      <div className="pe-dialog-head"><div><div className="pe-eyebrow">Ölçü düzenleme</div><h2>{target.title}</h2></div><button onClick={onClose}>Kapat</button></div>
      <div className="pe-form-grid">
        {Object.keys(target.values || {}).map((k) => <label key={k}><span>{k.replaceAll("_", " ")}</span><input className="pe-input" value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} /></label>)}
      </div>
      <div className="pe-dialog-actions"><button className="pe-btn pe-btn-secondary" onClick={onClose}>Vazgeç</button><button className="pe-btn pe-btn-primary" onClick={() => onSave(form)}>Kaydet</button></div>
    </div></div>
  );
}

export function RuleDialog({ target, products, onClose, onSave }) {
  const [type, setType] = useState("brand");
  const [value, setValue] = useState("");
  const [storage, setStorage] = useState("");
  const options = useMemo(() => {
    const key = type === "brand" ? "brand" : type === "category" ? "category_l1" : "category_l2";
    return [...new Set((products || []).map((p) => p[key]).filter(Boolean))].sort();
  }, [products, type]);
  if (!target) return null;
  const rule = { brand: "", category: "", subcategory: "", allowed_storage_type: storage };
  if (type === "brand") rule.brand = value;
  if (type === "category") rule.category = value;
  if (type === "subcategory") rule.subcategory = value;
  return (
    <div className="pe-modal-backdrop"><div className="pe-dialog">
      <div className="pe-dialog-head"><div><div className="pe-eyebrow">Kural atama</div><h2>{target.kind === "module" ? "Modül kuralı" : "Raf kuralı"}</h2></div><button onClick={onClose}>Kapat</button></div>
      <div className="pe-form-grid"><label><span>Kural tipi</span><select className="pe-input" value={type} onChange={(e) => { setType(e.target.value); setValue(""); }}><option value="brand">Marka</option><option value="category">Kategori</option><option value="subcategory">Alt kategori</option></select></label><label><span>Değer</span><select className="pe-input" value={value} onChange={(e) => setValue(e.target.value)}><option value="">Tümü</option>{options.map((o) => <option key={o} value={o}>{o}</option>)}</select></label>{target.kind === "shelf" && <label><span>Storage</span><select className="pe-input" value={storage} onChange={(e) => setStorage(e.target.value)}><option value="">Aynı kalsın</option><option value="AMBIENT">AMBIENT</option><option value="CHILLED">CHILLED</option><option value="FROZEN">FROZEN</option></select></label>}</div>
      <div className="pe-dialog-actions"><button className="pe-btn pe-btn-secondary" onClick={onClose}>Vazgeç</button><button className="pe-btn pe-btn-primary" onClick={() => onSave({ ...rule, label: `${type}: ${value || "Tümü"}` })}>Uygula</button></div>
    </div></div>
  );
}

export function ShelfRuleSort({ value, onChange, onApply }) {
  return <div className="pe-sort-rule"><select className="pe-input" value={value} onChange={(e) => onChange(e.target.value)}>{RULES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select><button className="pe-btn pe-btn-primary" onClick={onApply}>Bu rafı kurala göre diz</button></div>;
}
