import { fixtures, insights, products } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';

function Rules({ lang }) {
  return <div className="page"><div className="section-eyebrow">AI OPTIMIZATION CENTER</div><h1 style={{fontSize:42,margin:'8px 0'}}>Kural Motoru</h1><div className="grid cols-2"><div className="card pad"><h2>Operasyonel Planogram Motoru</h2><div className="form-grid"><div className="field"><label>Kural tipi</label><select><option>Marka</option><option>Kategori</option><option>Storage</option></select></div><div className="field"><label>Hedef zone</label><select><option>Kuru zone</option><option>+4 Soğuk</option><option>-18 Donuk</option></select></div><div className="field"><label>Öncelik</label><select><option>Normal</option><option>Yüksek</option></select></div><div className="field"><label>Davranış</label><select><option>Zone içine yerleştir</option><option>İzole et</option></select></div></div><button className="btn primary" style={{marginTop:16}}>Kural ekle ve uygula</button></div><div className="card pad"><h2>AI neden bunu önerdi?</h2><div className="grid cols-3"><div><b className="green">+12.4%</b><br/><span className="muted">Skor artışı</span></div><div><b className="green">+8.7%</b><br/><span className="muted">Satış artışı</span></div><div><b className="green">-9.3%</b><br/><span className="muted">Picking süresi</span></div></div><div className="list" style={{marginTop:16}}>{['Marka yan yana','Soğuk zincir izolasyonu','Ağır ürün sona','Hızlı SKU facing'].map(x=><div className="item" key={x}><b>{x}</b><button className="btn ghost">Uygula</button></div>)}</div></div></div></div>
}

function ProductLibrary({ lang }) {
  return <div className="page"><div className="section-eyebrow">DATA CENTER</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'library')}</h1><div className="card pad"><input className="search" placeholder="SKU, barkod, ürün, marka ara..."/><table className="table"><thead><tr><th>SKU</th><th>Ürün</th><th>Marka</th><th>Kategori</th><th>Storage</th><th>Satış</th><th>Facing</th></tr></thead><tbody>{products.map(p=><tr key={p.sku}><td>{p.sku}</td><td>{p.name}</td><td>{p.brand}</td><td>{p.category}</td><td><span className={`badge ${p.storage==='CHILLED'?'cyan':p.storage==='FROZEN'?'purple':'green'}`}>{p.storage}</span></td><td>{p.sales}</td><td>{p.facing}</td></tr>)}</tbody></table></div></div>
}

function FixtureLibrary({ lang }) {
  return <div className="page"><div className="section-eyebrow">FIXTURE LIBRARY</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'fixture')}</h1><div className="grid cols-2">{fixtures.map(f=><div className="card pad" key={f.id}><div className="section-eyebrow">{f.id}</div><h2>{f.name}</h2><p className="muted">{f.type} • {f.width}×{f.depth}×{f.height} cm • {f.shelves} raf</p><span className={`badge ${f.frozen?'purple':f.cold?'cyan':'green'}`}>{f.frozen?'FROZEN':f.cold?'CHILLED':'AMBIENT'}</span></div>)}</div></div>
}

function Delta({ lang }) {
  const rows = [['SKU-77881','A.1.2 → A.1.1','Facing 5 → 6','High'],['SKU-98712','C.2.1 → +4 Room','Zone correction','High'],['SKU-55431','A corridor → back ambient','Food isolation','Medium']];
  return <div className="page"><div className="section-eyebrow">DELTA PLANOGRAM</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'delta')}</h1><div className="card pad"><table className="table"><thead><tr><th>SKU</th><th>Taşıma</th><th>Değişiklik</th><th>Öncelik</th></tr></thead><tbody>{rows.map(r=><tr key={r[0]}>{r.map((c,i)=><td key={i}>{i===3?<span className="badge amber">{c}</span>:c}</td>)}</tr>)}</tbody></table></div></div>
}

function Publishing({ lang }) {
  return <div className="page"><div className="section-eyebrow">PUBLISHING</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'publishing')}</h1><div className="grid cols-3">{['Planogramı gördüm','Uygulamaya başladım','Fotoğraf yükledim'].map((x,i)=><div className="card kpi" key={x}><div className="kpi-label">{x}</div><div className="kpi-value">{[82,54,31][i]}%</div><div className="kpi-trend">Store compliance</div></div>)}</div><div className="card pad" style={{marginTop:22}}><div className="list">{['Anka uyguladı','Fulya fotoğraf bekliyor','Güven FR fixture eksik'].map(x=><div className="item" key={x}><b>{x}</b><span className="badge">Open</span></div>)}</div></div></div>
}

function Tasks({ lang }) {
  const tasks = ['Algida dolabı eksik','Soğuk oda kapasitesi yetersiz','Ürün ölçüsü eksik','Refill riski yüksek SKU','Fotoğraf bekleniyor'];
  return <div className="page"><div className="section-eyebrow">TASK MANAGEMENT</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'tasks')}</h1><div className="grid cols-2">{tasks.map((x,i)=><div className="item card" key={x}><div><b>{x}</b><div className="muted">Store: Anka • Deadline: {i+1} gün</div></div><span className={`badge ${i<2?'red':'amber'}`}>{i<2?'High':'Medium'}</span></div>)}</div></div>
}

function Reports({ lang }) {
  return <div className="page"><div className="section-eyebrow">EXECUTIVE VIEW</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'reports')}</h1><div className="grid cols-4">{['Risk','Capacity','Refill Cost','Implementation'].map((x,i)=><div className="card kpi" key={x}><div className="kpi-label">{x}</div><div className="kpi-value">{['Medium','87%','₺18.4K','54%'][i]}</div><div className="kpi-trend">Company view</div></div>)}</div><div className="card pad" style={{marginTop:22}}><h2>High Risk Stores</h2><div className="list">{insights.map(i=><div className="item" key={i.title}><b>{i.title}</b><span className={`badge ${i.tone}`}>{i.impact}</span></div>)}</div></div></div>
}

function Admin({ lang }) {
  return <div className="page"><div className="section-eyebrow">ADMIN</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'admin')}</h1><div className="grid cols-3"><div className="card pad"><h2>Store DNA</h2><p className="muted">Depo bazlı m², fixture, soğuk oda, donuk oda ve FR/Corporate bilgisi.</p></div><div className="card pad"><h2>User Roles</h2><p className="muted">USER, STORE_MANAGER, REGIONAL_MANAGER, ADMIN, SUPER_USER.</p></div><div className="card pad"><h2>API Status</h2><p className="muted">Backend hazır değilse mock fallback çalışır; endpoint yapısı korunur.</p></div></div></div>
}

export { Rules, ProductLibrary, FixtureLibrary, Delta, Publishing, Tasks, Reports, Admin };
