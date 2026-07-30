import { useEffect, useMemo, useState } from 'react';
import { api } from '../../services/api.js';

function aisleLabel(index) {
  let value = Number(index) + 1;
  let label = '';
  while (value > 0) {
    value -= 1;
    label = String.fromCharCode(65 + (value % 26)) + label;
    value = Math.floor(value / 26);
  }
  return label;
}

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
    aisle_id: aisleLabel(idx),
    left_modules: makeModules('L', data.left_modules, data.left_fixture_type),
    right_modules: makeModules('R', data.right_modules, data.right_fixture_type),
  }));
}

const COPY = {
  tr: {
    setup: 'DEPO DNA KURULUMU', title: 'Depo yapısını kur', subtitle: 'Koridor, modül, raf ve soğuk/donuk ekipman gerçekliğini seçili depo master’ından yönet.',
    easy: 'Kolay kurulum', template: 'Şablondan başla', free: 'Serbest düzenle', store: 'Depo', size: 'Depo tipi',
    aisle: 'Koridor sayısı', leftModules: 'Sol modül', rightModules: 'Sağ modül', leftType: 'Sol ekipman', rightType: 'Sağ ekipman',
    shelves: 'Modül başı raf', width: 'Raf genişliği', depth: 'Raf derinliği', height: 'Raf yüksekliği',
    equipment: 'Onaylı ekipman envanteri', chilledRoom: '+4 soğuk oda m²', frozenRoom: '-18 donuk oda m²',
    algida: 'Algida donuk dolabı', martek4: 'Martek +4', martek18: 'Martek -18', horizontal: 'Yatay -18',
    produce: 'Meyve-sebze rafı', greens: 'Yeşillik +8 rafı', newSteel: 'Yeni nesil çelik raf',
    preview: 'Canlı layout önizleme', save: 'Depo DNA’yı kaydet', saving: 'Kaydediliyor…', cancel: 'Vazgeç',
    inventory: 'Dolap envanterinden otomatik eşleşti', freeTitle: 'Serbest düzenleme', openEditor: 'Mimari Düzenleyici’yi aç',
  },
  en: {
    setup: 'STORE DNA SETUP', title: 'Configure depot structure', subtitle: 'Manage aisles, modules, shelves and cold/frozen fixtures from the selected depot master.',
    easy: 'Quick setup', template: 'Start from template', free: 'Free edit', store: 'Depot', size: 'Depot size',
    aisle: 'Aisle count', leftModules: 'Left modules', rightModules: 'Right modules', leftType: 'Left fixture', rightType: 'Right fixture',
    shelves: 'Shelves per module', width: 'Shelf width', depth: 'Shelf depth', height: 'Shelf height',
    equipment: 'Approved fixture inventory', chilledRoom: '+4 chilled room m²', frozenRoom: '-18 frozen room m²',
    algida: 'Algida freezer', martek4: 'Martek +4', martek18: 'Martek -18', horizontal: 'Horizontal -18',
    produce: 'Produce rack', greens: 'Greens +8 rack', newSteel: 'New generation steel rack',
    preview: 'Live layout preview', save: 'Save Store DNA', saving: 'Saving…', cancel: 'Cancel',
    inventory: 'Matched automatically from fixture inventory', freeTitle: 'Free editing', openEditor: 'Open Layout Architect',
  },
  de: {
    setup: 'LAGER-DNA EINRICHTUNG', title: 'Lagerstruktur konfigurieren', subtitle: 'Gänge, Module, Regale sowie Kühl- und Tiefkühlausstattung aus dem Lagermaster verwalten.',
    easy: 'Schnelleinrichtung', template: 'Mit Vorlage starten', free: 'Frei bearbeiten', store: 'Lager', size: 'Lagergröße',
    aisle: 'Anzahl Gänge', leftModules: 'Linke Module', rightModules: 'Rechte Module', leftType: 'Linke Ausstattung', rightType: 'Rechte Ausstattung',
    shelves: 'Regale je Modul', width: 'Regalbreite', depth: 'Regaltiefe', height: 'Regalhöhe',
    equipment: 'Freigegebener Ausstattungsbestand', chilledRoom: '+4 Kühlraum m²', frozenRoom: '-18 Tiefkühlraum m²',
    algida: 'Algida-Tiefkühler', martek4: 'Martek +4', martek18: 'Martek -18', horizontal: 'Horizontal -18',
    produce: 'Obst-/Gemüseregal', greens: 'Grünwaren +8', newSteel: 'Stahlregal neue Generation',
    preview: 'Live-Layoutvorschau', save: 'Lager-DNA speichern', saving: 'Speichern…', cancel: 'Abbrechen',
    inventory: 'Automatisch mit dem Ausstattungsbestand abgeglichen', freeTitle: 'Freie Bearbeitung', openEditor: 'Layout-Architekt öffnen',
  },
  ar: {
    setup: 'إعداد بيانات المستودع', title: 'إعداد بنية المستودع', subtitle: 'إدارة الممرات والوحدات والرفوف ومعدات التبريد والتجميد من سجل المستودع المحدد.',
    easy: 'إعداد سريع', template: 'البدء من قالب', free: 'تحرير حر', store: 'المستودع', size: 'حجم المستودع',
    aisle: 'عدد الممرات', leftModules: 'الوحدات اليسرى', rightModules: 'الوحدات اليمنى', leftType: 'المعدات اليسرى', rightType: 'المعدات اليمنى',
    shelves: 'الرفوف لكل وحدة', width: 'عرض الرف', depth: 'عمق الرف', height: 'ارتفاع الرف',
    equipment: 'سجل المعدات المعتمد', chilledRoom: 'مساحة غرفة +4', frozenRoom: 'مساحة غرفة -18',
    algida: 'مجمد Algida', martek4: 'Martek +4', martek18: 'Martek -18', horizontal: 'مجمد أفقي -18',
    produce: 'رف الخضار والفواكه', greens: 'رف الخضار +8', newSteel: 'رف فولاذي جديد',
    preview: 'معاينة مباشرة', save: 'حفظ بيانات المستودع', saving: 'جارٍ الحفظ…', cancel: 'إلغاء',
    inventory: 'تمت المطابقة تلقائيًا مع سجل المعدات', freeTitle: 'تحرير حر', openEditor: 'فتح مصمم التخطيط',
  },
};

function formDefaults(storeCode, storeName) {
  return {
    store_code: storeCode,
    store_name: storeName,
    warehouse_size: 'medium',
    aisle_count: 8,
    left_modules: 6,
    right_modules: 6,
    left_fixture_type: 'steel_rack',
    right_fixture_type: 'steel_rack',
    has_chilled_room: false,
    chilled_area_m2: 0,
    has_frozen_room: false,
    frozen_area_m2: 0,
    has_algida_fridge: false,
    algida_count: 0,
    has_horizontal_fridge: false,
    horizontal_fridge_count: 0,
    martek_plus4_count: 0,
    martek_frozen_count: 0,
    has_produce_shelf: false,
    produce_module_count: 0,
    produce_chilled_count: 0,
    new_gen_steel_rack_count: 0,
    has_receiving: true,
    has_dispatch: true,
    standard_rack_dimensions: { width: 100, depth: 50, height: 210 },
    shelves_per_rack: 6,
  };
}

export default function StoreDNASetupWizard({ lang = 'tr', storeCode = 'AUTO', storeName = 'Seçili Depo', storeProfile, initialDna, onComplete, onCancel, onOpenArchitect }) {
  const c = COPY[lang] || COPY.en;
  const [mode, setMode] = useState('easy');
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState(() => formDefaults(storeCode, storeName));

  useEffect(() => {
    const master = initialDna || storeProfile?.default_dna || {};
    const next = {
      ...formDefaults(storeCode, storeName),
      ...master,
      store_code: storeCode,
      store_name: storeName,
      standard_rack_dimensions: {
        ...formDefaults(storeCode, storeName).standard_rack_dimensions,
        ...(master.standard_rack_dimensions || {}),
      },
    };
    next.has_chilled_room = Number(next.chilled_area_m2 || 0) > 0;
    next.has_frozen_room = Number(next.frozen_area_m2 || 0) > 0;
    next.has_algida_fridge = Number(next.algida_count || 0) > 0;
    next.has_horizontal_fridge = Number(next.horizontal_fridge_count || 0) > 0;
    next.has_produce_shelf = Number(next.produce_module_count || 0) > 0;
    setData(next);
  }, [storeCode, storeName, storeProfile, initialDna]);

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
          <div className="section-eyebrow">{c.setup}</div>
          <h2>{c.title}</h2>
          <p className="muted">{c.subtitle}</p>
        </div>
        <div className="wizard-mode-tabs">
          <button className={mode === 'easy' ? 'active' : ''} onClick={() => setMode('easy')}>{c.easy}</button>
          <button className={mode === 'template' ? 'active' : ''} onClick={() => setMode('template')}>{c.template}</button>
          <button className={mode === 'free' ? 'active' : ''} onClick={() => setMode('free')}>{c.free}</button>
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
          <h3>{c.freeTitle}</h3>
          <p className="muted">3D / Layout Architect ekranında kolon, duvar, oda, raf ve dispatch alanlarını sürükleyerek düzenleyebilirsin. Kaydettiğinde Store DNA’ya yazılır.</p>
          <button className="btn primary" onClick={() => onOpenArchitect?.()}>{c.openEditor}</button>
        </div>
      )}

      {mode === 'easy' && (
        <div className="wizard-layout">
          <div className="wizard-form">
            <div className="field-grid two">
              <label>{c.store}<input value={data.store_name} readOnly /></label>
              <label>{c.size}<select value={data.warehouse_size} onChange={(e) => setField('warehouse_size', e.target.value)}><option value="small">S</option><option value="medium">M</option><option value="large">L</option></select></label>
              <label>{c.aisle}<input type="number" min="1" max="100" value={data.aisle_count} onChange={(e) => setField('aisle_count', Number(e.target.value))} /></label>
              <label>{c.leftModules}<input type="number" min="0" max="30" value={data.left_modules} onChange={(e) => setField('left_modules', Number(e.target.value))} /></label>
              <label>{c.rightModules}<input type="number" min="0" max="30" value={data.right_modules} onChange={(e) => setField('right_modules', Number(e.target.value))} /></label>
              <label>{c.leftType}<select value={data.left_fixture_type} onChange={(e) => setField('left_fixture_type', e.target.value)}>{fixtureTypes.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></label>
              <label>{c.rightType}<select value={data.right_fixture_type} onChange={(e) => setField('right_fixture_type', e.target.value)}>{fixtureTypes.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></label>
              <label>{c.shelves}<input type="number" min="1" max="12" value={data.shelves_per_rack} onChange={(e) => setField('shelves_per_rack', Number(e.target.value))} /></label>
            </div>

            <div className="field-grid three compact">
              <label>{c.width}<input type="number" value={data.standard_rack_dimensions.width} onChange={(e) => setData((p) => ({ ...p, standard_rack_dimensions: { ...p.standard_rack_dimensions, width: Number(e.target.value) }}))} /></label>
              <label>{c.depth}<input type="number" value={data.standard_rack_dimensions.depth} onChange={(e) => setData((p) => ({ ...p, standard_rack_dimensions: { ...p.standard_rack_dimensions, depth: Number(e.target.value) }}))} /></label>
              <label>{c.height}<input type="number" value={data.standard_rack_dimensions.height} onChange={(e) => setData((p) => ({ ...p, standard_rack_dimensions: { ...p.standard_rack_dimensions, height: Number(e.target.value) }}))} /></label>
            </div>

            <div className="fixture-count-panel">
              <div className="mini-section-title">{c.equipment}</div>
              <div className="field-grid three compact">
                <label>{c.chilledRoom}<input type="number" min="0" value={data.has_chilled_room ? data.chilled_area_m2 : 0} onChange={(e) => { setField('has_chilled_room', Number(e.target.value) > 0); setField('chilled_area_m2', Number(e.target.value)); }} /></label>
                <label>{c.frozenRoom}<input type="number" min="0" value={data.has_frozen_room ? data.frozen_area_m2 : 0} onChange={(e) => { setField('has_frozen_room', Number(e.target.value) > 0); setField('frozen_area_m2', Number(e.target.value)); }} /></label>
                <label>{c.algida}<input type="number" min="0" value={data.has_algida_fridge ? data.algida_count : 0} onChange={(e) => { setField('has_algida_fridge', Number(e.target.value) > 0); setField('algida_count', Number(e.target.value)); }} /></label>
                <label>{c.martek4}<input type="number" min="0" value={data.martek_plus4_count} onChange={(e) => setField('martek_plus4_count', Number(e.target.value))} /></label>
                <label>{c.martek18}<input type="number" min="0" value={data.martek_frozen_count} onChange={(e) => setField('martek_frozen_count', Number(e.target.value))} /></label>
                <label>{c.horizontal}<input type="number" min="0" value={data.has_horizontal_fridge ? data.horizontal_fridge_count : 0} onChange={(e) => { setField('has_horizontal_fridge', Number(e.target.value) > 0); setField('horizontal_fridge_count', Number(e.target.value)); }} /></label>
                <label>{c.produce}<input type="number" min="0" value={data.has_produce_shelf ? data.produce_module_count : 0} onChange={(e) => { setField('has_produce_shelf', Number(e.target.value) > 0); setField('produce_module_count', Number(e.target.value)); }} /></label>
                <label>{c.greens}<input type="number" min="0" value={data.produce_chilled_count} onChange={(e) => setField('produce_chilled_count', Number(e.target.value))} /></label>
                <label>{c.newSteel}<input type="number" min="0" value={data.new_gen_steel_rack_count} onChange={(e) => setField('new_gen_steel_rack_count', Number(e.target.value))} /></label>
              </div>
              <p className="inventory-source">✓ {c.inventory}: {storeProfile?.inventory_source || initialDna?.inventory_source || '—'}</p>
            </div>

            <div className="wizard-actions">
              {onCancel && <button className="btn ghost" onClick={onCancel}>{c.cancel}</button>}
              <button className="btn primary" disabled={saving || storeCode === 'AUTO'} onClick={saveEasy}>{saving ? c.saving : c.save}</button>
            </div>
          </div>

          <div className="wizard-preview">
            <div className="preview-title">{c.preview}</div>
            <div className="aisle-preview-list">
              {preview.map((a) => (
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
