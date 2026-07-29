import { useMemo, useState } from 'react';
import { api } from '../../services/api.js';

const aisleLetters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

const fixtureTypes = [
  { value: 'steel_rack', label: 'Regular Raf', zone: 'AMBIENT', width: 100, depth: 50, height: 210, shelves: 6 },
  { value: 'new_generation_steel_rack', label: 'Yeni Nesil Çelik Raf', zone: 'AMBIENT', width: 100, depth: 60, height: 250, shelves: 6 },
  { value: 'produce_shelf', label: 'Meyve Sebze Rafı', zone: 'PRODUCE', width: 120, depth: 60, height: 180, shelves: 4 },
  { value: 'horizontal_fridge', label: 'Yatay Dolap', zone: 'CHILLED', width: 150, depth: 70, height: 110, shelves: 3 },
  { value: 'martek_plus4', label: '+4 Dolap / Oda Rafı', zone: 'CHILLED', width: 150, depth: 55, height: 210, shelves: 5 },
  { value: 'martek_frozen_minus18', label: '-18 Donuk Raf', zone: 'FROZEN', width: 150, depth: 60, height: 210, shelves: 4 },
  { value: 'ice_cream_chest_freezer_medium', label: 'Algida Dolabı', zone: 'FROZEN', width: 120, depth: 70, height: 110, shelves: 3 },
  { value: 'hdr_heavy_rack', label: 'Ağır / Palet Rafı', zone: 'HEAVY', width: 120, depth: 80, height: 180, shelves: 3 },
];

const templates = [
  { id: 'small_darkstore', label: 'Küçük Darkstore', aisles: 4, left: 4, right: 4, chilled: true, frozen: true, algida: 2 },
  { id: 'medium_darkstore', label: 'Orta Darkstore', aisles: 8, left: 6, right: 6, chilled: true, frozen: true, algida: 4 },
  { id: 'large_darkstore', label: 'Büyük Darkstore', aisles: 12, left: 6, right: 6, chilled: true, frozen: true, algida: 5 },
  { id: 'produce_focus', label: 'Meyve Sebze Yoğun', aisles: 8, left: 6, right: 6, chilled: true, frozen: true, algida: 3, produce: true },
];

function makeModules(side, count, type) {
  const preset = fixtureTypes.find((x) => x.value === type) || fixtureTypes[0];
  return Array.from({ length: Number(count || 0) }, (_, idx) => ({
    id: `${side}${idx + 1}`,
    side,
    module_id: idx + 1,
    fixture_type: preset.value,
    label: `${side}-${idx + 1}`,
    zone: preset.zone,
    width_cm: preset.width,
    depth_cm: preset.depth,
    height_cm: preset.height,
    shelf_count: preset.shelves,
  }));
}

function buildPreviewAisles(data) {
  return Array.from({ length: Number(data.aisle_count || 1) }, (_, idx) => ({
    aisle_id: aisleLetters[idx] || `A${idx + 1}`,
    left_modules: makeModules('L', data.left_modules, data.left_fixture_type),
    right_modules: makeModules('R', data.right_modules, data.right_fixture_type),
  }));
}

export default function StoreDNASetupWizard({ storeCode = 'AUTO', storeName = 'Seçili Depo', onComplete, onCancel, onOpenArchitect }) {
  const [mode, setMode] = useState('easy');
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState({
    store_code: storeCode,
    store_name: storeName,
    warehouse_size: 'medium',
    aisle_count: 8,
    left_modules: 6,
    right_modules: 6,
    left_fixture_type: 'steel_rack',
    right_fixture_type: 'steel_rack',
    has_chilled_room: true,
    chilled_area_m2: 12,
    has_frozen_room: true,
    frozen_area_m2: 8,
    has_algida_fridge: true,
    algida_count: 5,
    has_horizontal_fridge: true,
    horizontal_fridge_count: 1,
    martek_plus4_count: 4,
    martek_frozen_count: 2,
    has_produce_shelf: true,
    produce_module_count: 4,
    produce_chilled_count: 1,
    new_gen_steel_rack_count: 0,
    has_receiving: true,
    has_dispatch: true,
    standard_rack_dimensions: { width: 100, depth: 50, height: 210 },
    shelves_per_rack: 6,
  });

  const preview = useMemo(() => buildPreviewAisles(data), [data]);

  function setField(key, value) {
    setData((prev) => ({ ...prev, [key]: value }));
  }

  function applyTemplate(t) {
    setData((prev) => ({
      ...prev,
      aisle_count: t.aisles,
      left_modules: t.left,
      right_modules: t.right,
      has_chilled_room: t.chilled,
      has_frozen_room: t.frozen,
      has_algida_fridge: t.algida > 0,
      algida_count: t.algida,
      has_produce_shelf: Boolean(t.produce),
      selected_template: t.id,
    }));
    setMode('easy');
  }

  async function saveEasy() {
    setSaving(true);
    try {
      const payload = {
        ...data,
        num_ambient_aisles: Number(data.aisle_count),
        left_modules_per_aisle: Number(data.left_modules || 0),
        right_modules_per_aisle: Number(data.right_modules || 0),
        left_fixture_type: data.left_fixture_type,
        right_fixture_type: data.right_fixture_type,
        standard_rack_dimensions: {
          width: Number(data.standard_rack_dimensions.width || 100),
          depth: Number(data.standard_rack_dimensions.depth || 50),
          height: Number(data.standard_rack_dimensions.height || 210),
        },
        shelves_per_rack: Number(data.shelves_per_rack || 6),
        aisle_module_config: preview,
        algida_count: Number(data.has_algida_fridge ? data.algida_count || 0 : 0),
        horizontal_fridge_count: Number(data.has_horizontal_fridge ? data.horizontal_fridge_count || 0 : 0),
        martek_plus4_count: Number(data.martek_plus4_count || 0),
        martek_frozen_count: Number(data.martek_frozen_count || 0),
        produce_module_count: Number(data.has_produce_shelf ? data.produce_module_count || 0 : 0),
        produce_chilled_count: Number(data.produce_chilled_count || 0),
        new_gen_steel_rack_count: Number(data.new_gen_steel_rack_count || 0),
      };
      const result = await api.generateStoreDnaEasy(storeCode, payload);
      if (result.status !== 'success') throw new Error(result.message || 'Store DNA oluşturulamadı.');
      onComplete?.(result.dna);
    } catch (err) {
      alert(err.message || 'Store DNA kaydedilemedi.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="store-dna-wizard card pad">
      <div className="wizard-head">
        <div>
          <div className="section-eyebrow">STORE DNA SETUP</div>
          <h2>Depo yapısını kur</h2>
          <p className="muted">Planogram üretmeden önce koridor, modül, raf ve soğuk/donuk alan gerçekliğini kaydedelim.</p>
        </div>
        <div className="wizard-mode-tabs">
          <button className={mode === 'easy' ? 'active' : ''} onClick={() => setMode('easy')}>Kolay Kurulum</button>
          <button className={mode === 'template' ? 'active' : ''} onClick={() => setMode('template')}>Şablondan Başla</button>
          <button className={mode === 'free' ? 'active' : ''} onClick={() => setMode('free')}>Serbest Düzenle</button>
        </div>
      </div>

      {mode === 'template' && (
        <div className="template-grid">
          {templates.map((t) => (
            <button key={t.id} className="template-card" onClick={() => applyTemplate(t)}>
              <b>{t.label}</b>
              <span>{t.aisles} koridor · {t.left}+{t.right} modül · Algida {t.algida}</span>
            </button>
          ))}
        </div>
      )}

      {mode === 'free' && (
        <div className="wizard-free-box">
          <h3>Serbest düzenleme</h3>
          <p className="muted">3D / Layout Architect ekranında kolon, duvar, oda, raf ve dispatch alanlarını sürükleyerek düzenleyebilirsin. Kaydettiğinde Store DNA’ya yazılır.</p>
          <button className="btn primary" onClick={() => onOpenArchitect?.()}>Layout Architect’e git</button>
        </div>
      )}

      {mode === 'easy' && (
        <div className="wizard-layout">
          <div className="wizard-form">
            <div className="field-grid two">
              <label>Depo adı<input value={data.store_name} onChange={(e) => setField('store_name', e.target.value)} /></label>
              <label>Depo tipi<select value={data.warehouse_size} onChange={(e) => setField('warehouse_size', e.target.value)}><option value="small">Küçük</option><option value="medium">Orta</option><option value="large">Büyük</option></select></label>
              <label>Koridor sayısı<input type="number" min="1" max="24" value={data.aisle_count} onChange={(e) => setField('aisle_count', Number(e.target.value))} /></label>
              <label>Sol modül sayısı<input type="number" min="0" max="12" value={data.left_modules} onChange={(e) => setField('left_modules', Number(e.target.value))} /></label>
              <label>Sağ modül sayısı<input type="number" min="0" max="12" value={data.right_modules} onChange={(e) => setField('right_modules', Number(e.target.value))} /></label>
              <label>Sol modül tipi<select value={data.left_fixture_type} onChange={(e) => setField('left_fixture_type', e.target.value)}>{fixtureTypes.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></label>
              <label>Sağ modül tipi<select value={data.right_fixture_type} onChange={(e) => setField('right_fixture_type', e.target.value)}>{fixtureTypes.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></label>
              <label>Modül başı raf<input type="number" min="3" max="8" value={data.shelves_per_rack} onChange={(e) => setField('shelves_per_rack', Number(e.target.value))} /></label>
            </div>

            <div className="field-grid three compact">
              <label>Raf genişliği<input type="number" value={data.standard_rack_dimensions.width} onChange={(e) => setData((p) => ({ ...p, standard_rack_dimensions: { ...p.standard_rack_dimensions, width: Number(e.target.value) }}))} /></label>
              <label>Raf derinliği<input type="number" value={data.standard_rack_dimensions.depth} onChange={(e) => setData((p) => ({ ...p, standard_rack_dimensions: { ...p.standard_rack_dimensions, depth: Number(e.target.value) }}))} /></label>
              <label>Raf yüksekliği<input type="number" value={data.standard_rack_dimensions.height} onChange={(e) => setData((p) => ({ ...p, standard_rack_dimensions: { ...p.standard_rack_dimensions, height: Number(e.target.value) }}))} /></label>
            </div>

            <div className="fixture-count-panel">
              <div className="mini-section-title">Özel ekipman adetleri</div>
              <div className="field-grid three compact">
                <label>+4 Soğuk oda m²<input type="number" min="0" value={data.has_chilled_room ? data.chilled_area_m2 : 0} onChange={(e) => { setField('has_chilled_room', Number(e.target.value) > 0); setField('chilled_area_m2', Number(e.target.value)); }} /></label>
                <label>-18 Donuk oda m²<input type="number" min="0" value={data.has_frozen_room ? data.frozen_area_m2 : 0} onChange={(e) => { setField('has_frozen_room', Number(e.target.value) > 0); setField('frozen_area_m2', Number(e.target.value)); }} /></label>
                <label>Algida dolabı<input type="number" min="0" value={data.has_algida_fridge ? data.algida_count : 0} onChange={(e) => { setField('has_algida_fridge', Number(e.target.value) > 0); setField('algida_count', Number(e.target.value)); }} /></label>
                <label>Martek +4 dolap<input type="number" min="0" value={data.martek_plus4_count} onChange={(e) => setField('martek_plus4_count', Number(e.target.value))} /></label>
                <label>Martek -18 dolap<input type="number" min="0" value={data.martek_frozen_count} onChange={(e) => setField('martek_frozen_count', Number(e.target.value))} /></label>
                <label>Yatay donuk dolap<input type="number" min="0" value={data.has_horizontal_fridge ? data.horizontal_fridge_count : 0} onChange={(e) => { setField('has_horizontal_fridge', Number(e.target.value) > 0); setField('horizontal_fridge_count', Number(e.target.value)); }} /></label>
                <label>Meyve-sebze kasa rafı<input type="number" min="0" value={data.has_produce_shelf ? data.produce_module_count : 0} onChange={(e) => { setField('has_produce_shelf', Number(e.target.value) > 0); setField('produce_module_count', Number(e.target.value)); }} /></label>
                <label>Yeşillik +8 rafı<input type="number" min="0" value={data.produce_chilled_count} onChange={(e) => setField('produce_chilled_count', Number(e.target.value))} /></label>
                <label>Yeni nesil çelik raf<input type="number" min="0" value={data.new_gen_steel_rack_count} onChange={(e) => setField('new_gen_steel_rack_count', Number(e.target.value))} /></label>
              </div>
              <p className="muted small">Checkbox yok: engine kapasiteyi adet ve ölçüyle hesaplar. 9 Algida varsa Store DNA içinde 9 ayrı fixture instance oluşur.</p>
            </div>

            <div className="wizard-actions">
              {onCancel && <button className="btn ghost" onClick={onCancel}>Vazgeç</button>}
              <button className="btn primary" disabled={saving} onClick={saveEasy}>{saving ? 'Kaydediliyor...' : 'Store DNA’yı kaydet'}</button>
            </div>
          </div>

          <div className="wizard-preview">
            <div className="preview-title">Canlı layout önizleme</div>
            <div className="aisle-preview-list">
              {preview.slice(0, 12).map((a) => (
                <div key={a.aisle_id} className="aisle-preview-row">
                  <b>{a.aisle_id}</b>
                  <span className="module-line">Sol {a.left_modules.length}</span>
                  <span className="module-line right">Sağ {a.right_modules.length}</span>
                </div>
              ))}
            </div>
            <div className="fixture-legend">
              <span><i className="dot ambient" /> Ambient</span>
              <span><i className="dot chilled" /> +4</span>
              <span><i className="dot frozen" /> -18 / Algida</span>
              <span>Algida {data.has_algida_fridge ? data.algida_count : 0}</span>
              <span>Martek +4 {data.martek_plus4_count}</span>
              <span><i className="dot produce" /> Meyve Sebze</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
