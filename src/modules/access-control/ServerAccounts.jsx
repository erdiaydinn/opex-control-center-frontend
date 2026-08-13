import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPatch, apiPost } from "../../api/client.js";
import "./server-accounts.css";

const EMPTY_USER = { username: "", name: "", password: "", roles: ["counter"], warehouse_ids: [], active: true, force_password_change: true };
const EMPTY_WAREHOUSE = { code: "", name: "", server_group: "primary", active: true };

export default function ServerAccounts() {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [userForm, setUserForm] = useState(EMPTY_USER);
  const [warehouseForm, setWarehouseForm] = useState(EMPTY_WAREHOUSE);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(true);

  async function load() {
    setBusy(true);
    try {
      const [u, w] = await Promise.all([apiGet("/identity/admin/users"), apiGet("/identity/admin/warehouses")]);
      setUsers(u.rows || []); setWarehouses(w.rows || []); setMessage("");
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  }
  useEffect(() => { load(); }, []);

  const activeWarehouses = useMemo(() => warehouses.filter((item) => item.active), [warehouses]);
  function toggleWarehouse(id) {
    setUserForm((current) => ({ ...current, warehouse_ids: current.warehouse_ids.includes(id)
      ? current.warehouse_ids.filter((value) => value !== id) : [...current.warehouse_ids, id] }));
  }
  async function createWarehouse(event) {
    event.preventDefault(); setMessage("");
    try { await apiPost("/identity/admin/warehouses", warehouseForm); setWarehouseForm(EMPTY_WAREHOUSE); await load(); }
    catch (error) { setMessage(error.message); }
  }
  async function createUser(event) {
    event.preventDefault(); setMessage("");
    try { await apiPost("/identity/admin/users", userForm); setUserForm(EMPTY_USER); await load(); }
    catch (error) { setMessage(error.message); }
  }
  async function toggleUser(user) {
    try { await apiPatch(`/identity/admin/users/${user.id}`, { active: !user.active }); await load(); }
    catch (error) { setMessage(error.message); }
  }

  return <main className="server-accounts">
    <header>
      <button onClick={() => navigate("/inventory")}>← Inventory'ye dön</button>
      <div><span>INVENTORY ADMINISTRATION</span><h1>Sayım kullanıcıları ve depolar</h1>
        <p>Bu alan yalnızca Inventory sayım hesaplarını, depo kapsamını ve sunucu grubunu yönetir. OPEX platform erişimi vermez.</p></div>
    </header>
    {message && <div className="account-alert" role="alert">{message}</div>}
    <section className="account-grid">
      <form onSubmit={createWarehouse}>
        <h2>Depo oluştur</h2>
        <label>Depo kodu<input required value={warehouseForm.code} onChange={(e) => setWarehouseForm({ ...warehouseForm, code: e.target.value })} /></label>
        <label>Depo adı<input required value={warehouseForm.name} onChange={(e) => setWarehouseForm({ ...warehouseForm, name: e.target.value })} /></label>
        <label>Ana sunucu grubu<input required value={warehouseForm.server_group} onChange={(e) => setWarehouseForm({ ...warehouseForm, server_group: e.target.value })} /></label>
        <button className="primary" disabled={busy}>Depoyu oluştur</button>
      </form>
      <form onSubmit={createUser}>
        <h2>Sayım hesabı oluştur</h2>
        <label>Kullanıcı adı / e-posta<input required value={userForm.username} onChange={(e) => setUserForm({ ...userForm, username: e.target.value })} /></label>
        <label>Ad soyad<input required value={userForm.name} onChange={(e) => setUserForm({ ...userForm, name: e.target.value })} /></label>
        <label>Tek kullanımlık parola<input required minLength="12" type="password" value={userForm.password} onChange={(e) => setUserForm({ ...userForm, password: e.target.value })} /></label>
        <label>Rol<select value={userForm.roles[0]} onChange={(e) => setUserForm({ ...userForm, roles: [e.target.value] })}>
          <option value="counter">Sayım personeli</option><option value="warehouse_manager">Depo yöneticisi</option>
          <option value="regional_manager">Bölge yöneticisi</option><option value="inventory_control">Merkez operasyon</option>
          <option value="auditor">Denetçi</option><option value="admin">Admin</option>
        </select></label>
        <fieldset><legend>Bağlı depolar</legend>{activeWarehouses.map((warehouse) =>
          <label className="check" key={warehouse.id}><input type="checkbox" checked={userForm.warehouse_ids.includes(warehouse.id)}
            onChange={() => toggleWarehouse(warehouse.id)} />{warehouse.code} · {warehouse.name}</label>)}</fieldset>
        <button className="primary" disabled={busy}>Güvenli hesabı oluştur</button>
      </form>
    </section>
    <section className="account-table"><h2>Inventory sayım hesapları</h2>
      {busy ? <p>Yükleniyor…</p> : <table><thead><tr><th>Kullanıcı</th><th>Rol</th><th>Depo kapsamı</th><th>Durum</th><th /></tr></thead>
        <tbody>{users.map((user) => <tr key={user.id}><td><strong>{user.name}</strong><small>{user.username}</small></td>
          <td>{user.roles.join(", ")}</td><td>{user.warehouse_scope.join(", ") || "Global / depo atanmamış"}</td>
          <td>{user.active ? "Aktif" : "Pasif"}</td><td><button onClick={() => toggleUser(user)}>{user.active ? "Pasife al" : "Aktifleştir"}</button></td></tr>)}</tbody></table>}
    </section>
  </main>;
}
