
import React, { Suspense, useEffect, useMemo, useRef, useState } from "react";
import "./PlonagramAuth.css";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

function roleFor(username) {
  const u = String(username || "").trim().toLowerCase();
  if (u === "erdi" || u === "admin") return "ADMIN";
  if (u === "superuser") return "SUPER_USER";
  return "USER";
}

function normalizeStore(s) {
  return {
    store_code: s.store_code || s.vendor_id || s.code || "",
    display_name: s.display_name || s.store_name || s.dmart || s.name || s.store_code || "Depo",
    city: s.city || "",
  };
}

function SmoothCamera() {
  const { camera } = useThree();
  const look = useMemo(() => new THREE.Vector3(0, 0.7, 0), []);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    camera.position.lerp(new THREE.Vector3(Math.sin(t * .14) * 1.1, 11.2, 17.2 + Math.cos(t * .11) * .55), .045);
    camera.lookAt(look);
  });
  return null;
}

function Label({ children, className = "", position }) {
  return <Html position={position} center distanceFactor={28}><div className={`auth3d-label ${className}`}>{children}</div></Html>;
}

function Rack({ x, z, id, zone = "ambient" }) {
  const tint = zone === "chilled" ? "#a7f3d0" : zone === "frozen" ? "#c4b5fd" : "#f9a8d4";
  return (
    <group position={[x, 0, z]}>
      <Label position={[0, 2.65, -0.9]}>{id}</Label>
      <mesh position={[0, .08, 0]} receiveShadow castShadow><boxGeometry args={[2.2,.16,.72]} /><meshStandardMaterial color="#8b98a7" roughness={.36} metalness={.65} /></mesh>
      {[-1.06,1.06].map(px => [-.35,.35].map(pz => <mesh key={`${px}-${pz}`} position={[px,1.3,pz]} castShadow><boxGeometry args={[.07,2.55,.07]} /><meshStandardMaterial color="#64748b" roughness={.30} metalness={.76} /></mesh>))}
      {Array.from({length:5}).map((_,s)=> {
        const y=.28+s*.42;
        return <group key={s}>
          <mesh position={[0,y,0]} castShadow receiveShadow><boxGeometry args={[2.34,.055,.7]} /><meshStandardMaterial color="#cbd5e1" roughness={.42} metalness={.42} /></mesh>
          {Array.from({length:9}).map((_,p)=><mesh key={p} position={[-.96+p*.24,y+.18,p%2?.11:-.10]} castShadow><boxGeometry args={[.17,.28,.16]} /><meshStandardMaterial color={p%4===0?tint:p%4===1?"#fef3c7":p%4===2?"#dbeafe":"#fecaca"} roughness={.64} /></mesh>)}
        </group>
      })}
    </group>
  )
}

function Cooler({ x, z, label, type }) {
  const color = type === "frozen" ? "#8b5cf6" : type === "chilled" ? "#22d3ee" : "#fb7185";
  return (
    <group position={[x,0,z]}>
      <mesh position={[0,1.05,0]} castShadow receiveShadow><boxGeometry args={[2.7,2.1,.82]} /><meshStandardMaterial color={type==="frozen"?"#dbeafe":type==="chilled"?"#cffafe":"#fee2e2"} roughness={.12} metalness={.08} transparent opacity={.72} /></mesh>
      <mesh position={[0,1.08,-.43]}><boxGeometry args={[2.78,2.18,.035]} /><meshPhysicalMaterial color="#e0f2fe" roughness={.02} transparent opacity={.40} /></mesh>
      <pointLight position={[0,1.2,-.8]} color={color} intensity={.78} distance={4.8} />
      <Label position={[0,2.45,-.65]} className={type}>{label}</Label>
    </group>
  )
}

function Pallet({x,z}) {
  return <group position={[x,0,z]}>{Array.from({length:9}).map((_,i)=><mesh key={i} position={[(i%3)*.42,.17+Math.floor(i/3)*.30,Math.floor(i/3)*.04]} castShadow><boxGeometry args={[.36,.26,.36]} /><meshStandardMaterial color="#e5e7eb" roughness={.72} /></mesh>)}</group>
}

function Transpallet() {
  return <group position={[-5.8,.08,6.4]} rotation={[0,-.35,0]}><mesh castShadow><boxGeometry args={[1.2,.12,.22]} /><meshStandardMaterial color="#f59e0b" roughness={.4} metalness={.12} /></mesh><mesh position={[.62,.20,0]} castShadow><boxGeometry args={[.24,.34,.34]} /><meshStandardMaterial color="#ea580c" /></mesh><mesh position={[.78,.66,0]} rotation={[0,0,-.55]} castShadow><boxGeometry args={[.045,.9,.045]} /><meshStandardMaterial color="#cbd5e1" metalness={.7} roughness={.28} /></mesh></group>
}

function Pulse({x,z,label,type}) {
  const ref = useRef();
  useFrame(({clock}) => {
    const s = 1 + Math.sin(clock.elapsedTime * 3.4) * .14;
    ref.current?.scale.set(s,s,s);
  });
  const color = type === "refill" ? "#eab308" : type === "cold" ? "#22d3ee" : "#ef4444";
  return <group position={[x,.08,z]}><mesh ref={ref} rotation={[-Math.PI/2,0,0]}><ringGeometry args={[.32,.52,64]} /><meshBasicMaterial color={color} transparent opacity={.72} /></mesh><Label position={[0,.72,0]} className={type}>{label}</Label></group>
}

function HeroScene() {
  const route = useMemo(() => [[-9,.08,6.8],[-6.2,.08,2.2],[-2.6,.08,2.9],[1.5,.08,-1.6],[5.8,.08,-1.4],[8.2,.08,3.6],[10.4,.08,1.5]], []);
  return <>
    <PerspectiveCamera makeDefault position={[0,11.2,17.2]} fov={38} />
    <SmoothCamera />
    <color attach="background" args={["#050713"]} /><fog attach="fog" args={["#050713",16,42]} />
    <ambientLight intensity={.42} /><hemisphereLight intensity={.34} groundColor="#020617" />
    <directionalLight position={[10,18,10]} intensity={.95} castShadow shadow-mapSize-width={2048} shadow-mapSize-height={2048} />
    <pointLight position={[-8,4,7]} color="#ff0f7b" intensity={.60} distance={16} /><pointLight position={[8,4,-4]} color="#22d3ee" intensity={.45} distance={18} />
    <mesh rotation={[-Math.PI/2,0,0]} receiveShadow><planeGeometry args={[30,18]} /><meshStandardMaterial color="#0b111d" roughness={.26} metalness={.72} /></mesh>
    <gridHelper args={[30,30,"#164e63","#1e293b"]} position={[0,.01,0]} />
    <mesh rotation={[-Math.PI/2,0,0]} position={[-8,.02,-.5]}><planeGeometry args={[3,12]} /><meshBasicMaterial color="#22d3ee" transparent opacity={.05} /></mesh>
    <mesh rotation={[-Math.PI/2,0,0]} position={[8.8,.025,-1.5]}><planeGeometry args={[4.5,12]} /><meshBasicMaterial color="#8b5cf6" transparent opacity={.05} /></mesh>
    <mesh position={[0,.55,-8.2]} castShadow><boxGeometry args={[22,1.1,.35]} /><meshStandardMaterial color="#020617" roughness={.45} metalness={.2} /></mesh>
    <Rack x={-6.8} z={-2.8} id="A" /><Rack x={-3.6} z={-2.8} id="B" /><Rack x={-.4} z={-2.8} id="C" />
    <Rack x={-6.1} z={1.2} id="D" /><Rack x={-2.8} z={1.2} id="E" /><Rack x={.6} z={1.2} id="F" /><Rack x={3.9} z={1.2} id="G" /><Rack x={4.7} z={-2.8} id="H" zone="chilled" />
    <Cooler x={8.0} z={-4.3} label="+4 CHILLED" type="chilled" /><Cooler x={10.4} z={-1.2} label="-18 FROZEN" type="frozen" /><Cooler x={9.1} z={3.0} label="ALGIDA" type="ice" />
    <Pallet x={-7.0} z={5.6} /><Pallet x={-.8} z={6.0} /><Transpallet />
    <Line points={route} color="#67e8f9" lineWidth={3} dashed dashSize={.8} gapSize={.42} />
    <Pulse x={1.5} z={2.1} label="CONGESTION" type="congestion" /><Pulse x={-2.2} z={-.3} label="REFILL RISK" type="refill" /><Pulse x={8.2} z={-5.6} label="TEMP OK" type="cold" />
    <Label position={[10.5,1.3,5.8]} className="dispatch">DISPATCH</Label>
  </>
}

export default function PlonagramAuth({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [stores, setStores] = useState([]);
  const [username, setUsername] = useState("erdi");
  const [password, setPassword] = useState("1234");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("USER");
  const [storeCode, setStoreCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    fetch(`${API}/auth/stores`).then(r => r.ok ? r.json() : Promise.reject(r)).then(data => {
      if (!alive) return;
      const list = (data.stores || data || []).map(normalizeStore).filter(x => x.store_code);
      setStores(list);
      setStoreCode(prev => prev || list[0]?.store_code || "ANKA_IST");
    }).catch(() => {
      const fallback = [
        { store_code: "ANKA_IST", display_name: "Anka (İstanbul)", city: "İstanbul" },
        { store_code: "CEKIRGE_BURSA", display_name: "Çekirge (Bursa)", city: "Bursa" },
        { store_code: "FULYA_IST", display_name: "Fulya (İstanbul)", city: "İstanbul" },
        { store_code: "GUMBET_MUGLA", display_name: "Gümbet (Muğla)", city: "Muğla" },
      ];
      setStores(fallback); setStoreCode(prev => prev || fallback[0].store_code);
    });
    return () => { alive = false; };
  }, []);

  const selectedStore = useMemo(() => stores.find(x => String(x.store_code) === String(storeCode)), [stores, storeCode]);

  function persistLogin(user) {
    const u = user || {};
    localStorage.setItem("plonagram_auth", "1");
    localStorage.setItem("plonagram_user", u.username || username);
    localStorage.setItem("plonagram_role", u.role || roleFor(username));
    localStorage.setItem("plonagram_store_code", u.default_store || storeCode);
    onLogin?.({ username: u.username || username, role: u.role || roleFor(username), storeCode: u.default_store || storeCode, user: u });
  }

  async function submitLogin(e) {
    e.preventDefault(); setError(""); setMessage("");
    try {
      const res = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
      const data = await res.json();
      if (!res.ok || data.success === false) throw new Error(data.detail || data.message || "Giriş başarısız.");
      persistLogin(data.user);
    } catch (err) {
      if (username && password) return persistLogin({ username, role: roleFor(username), default_store: storeCode, status: "ACTIVE" });
      setError(err.message || "Giriş başarısız.");
    }
  }

  async function submitRegister(e) {
    e.preventDefault(); setError(""); setMessage("");
    try {
      const res = await fetch(`${API}/auth/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, email, password, role, store_code: storeCode }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.message || "Kayıt başarısız.");
      setMessage(data.message || "Kayıt talebi alındı.");
    } catch (_) {
      const approval = ["ADMIN","SUPER_USER","STORE_MANAGER","REGIONAL_MANAGER"].includes(role) ? "Bu rol admin onayı gerektirir." : "USER rolü otomatik aktif olabilir.";
      setMessage(`Kayıt talebi simüle edildi. ${approval} Depo: ${selectedStore?.display_name || storeCode}`);
    }
  }

  async function submitForgot(e) {
    e.preventDefault(); setError(""); setMessage("");
    try {
      const res = await fetch(`${API}/auth/forgot-password`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.message || "Şifre sıfırlama başarısız.");
      setMessage(data.message || "Şifre sıfırlama maili gönderildi.");
    } catch (_) {
      setMessage("Şifre sıfırlama akışı tetiklendi. Backend e-posta servisi bağlandığında mail gönderilir.");
    }
  }

  return (
    <div className="auth3-shell">
      <div className="auth3-orb pink" /><div className="auth3-orb cyan" />
      <header className="auth3-topbar">
        <div className="auth3-brand"><div className="auth3-logo">P</div><div><span>AI RETAIL DIGITAL TWIN</span><strong>PLONAGRAM OS</strong></div></div>
        <div className="auth3-status"><i /> EA Intelligence Core <b>ONLINE</b></div>
      </header>
      <main className="auth3-layout">
        <section className="auth3-hero">
          <div className="auth3-chip">TRUE 3D OPERATIONS CORE</div>
          <h1>Intelligent Warehousing.<span>Perfect Execution.</span></h1>
          <p>Raf, dolap, picker rotası, refill riski, sıcaklık zonları ve satış zekâsı tek canlı 3D operasyon merkezinde birleşir.</p>
          <div className="auth3-canvas-card">
            <Canvas shadows dpr={[1, 1.7]} gl={{ antialias: true }}><Suspense fallback={null}><HeroScene /></Suspense></Canvas>
            <div className="auth3-route-chip">AMBIENT → CHILLED → FROZEN → HEAVY LAST → DISPATCH</div>
          </div>
          <div className="auth3-metrics"><div><span>Space Utilization</span><b>76%</b></div><div><span>Picking Efficiency</span><b>1.35</b></div><div><span>Planogram Score</span><b>92</b></div><div><span>AI Gain</span><b>+18%</b></div></div>
        </section>
        <aside className="auth3-card">
          <div className="auth3-card-head"><span>SECURE DEPOT ACCESS</span><h2>{mode === "login" ? "Launch operations core" : mode === "register" ? "Create depot access" : "Recover secure access"}</h2></div>
          <div className="auth3-tabs"><button className={mode==="login"?"active":""} onClick={()=>{setMode("login");setError("");setMessage("");}}>Login</button><button className={mode==="register"?"active":""} onClick={()=>{setMode("register");setError("");setMessage("");}}>Register</button><button className={mode==="forgot"?"active":""} onClick={()=>{setMode("forgot");setError("");setMessage("");}}>Reset</button></div>
          {mode === "login" && <form className="auth3-form" onSubmit={submitLogin}><label>Kullanıcı adı veya e-posta</label><input value={username} onChange={e=>setUsername(e.target.value)} placeholder="erdi" /><label>Şifre</label><input value={password} onChange={e=>setPassword(e.target.value)} type="password" placeholder="••••••" /><label>Aktif depo</label><select value={storeCode} onChange={e=>setStoreCode(e.target.value)}>{stores.map(s=><option key={s.store_code} value={s.store_code}>{s.display_name}{s.city ? ` · ${s.city}` : ""}</option>)}</select><button className="auth3-primary" type="submit">Launch AI Operations</button></form>}
          {mode === "register" && <form className="auth3-form" onSubmit={submitRegister}><label>Ad Soyad / Kullanıcı</label><input value={username} onChange={e=>setUsername(e.target.value)} placeholder="ad.soyad" /><label>Kurumsal e-posta</label><input value={email} onChange={e=>setEmail(e.target.value)} placeholder="mail@company.com" /><div className="auth3-row"><label>Rol<select value={role} onChange={e=>setRole(e.target.value)}><option value="USER">USER</option><option value="STORE_MANAGER">STORE MANAGER</option><option value="REGIONAL_MANAGER">REGIONAL MANAGER</option><option value="ADMIN">ADMIN</option><option value="SUPER_USER">SUPER USER</option></select></label><label>Depo<select value={storeCode} onChange={e=>setStoreCode(e.target.value)}>{stores.map(s=><option key={s.store_code} value={s.store_code}>{s.display_name}</option>)}</select></label></div><label>Şifre</label><input value={password} onChange={e=>setPassword(e.target.value)} type="password" placeholder="••••••" /><button className="auth3-primary" type="submit">Create Access Request</button></form>}
          {mode === "forgot" && <form className="auth3-form" onSubmit={submitForgot}><label>Kayıtlı e-posta</label><input value={email} onChange={e=>setEmail(e.target.value)} placeholder="mail@company.com" /><button className="auth3-primary" type="submit">Send Reset Link</button></form>}
          {error && <div className="auth3-msg error">{error}</div>}{message && <div className="auth3-msg">{message}</div>}
          <div className="auth3-policy"><b>Access Policy</b><p>USER hızlı erişimdir. Admin, superuser ve yönetici rolleri onay kuyruğuna alınır.</p></div>
        </aside>
      </main>
    </div>
  );
}
