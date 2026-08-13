import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Copy,
  KeyRound,
  Lock,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { apiPost } from "../../api/client.js";
import {
  ACCESS_MODULES,
  DEFAULT_ACCESS_CONFIG,
  MODULE_DETAIL_CONFIG,
  refreshAccessConfig,
  SCOPE_OPTIONS,
} from "../../auth/accessConfig.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import "./access-control.css";

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function normalizeEmail(email) {
  return String(email || "").trim().toLowerCase();
}

function normalizeGroupId(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/ğ/g, "g")
    .replace(/ü/g, "u")
    .replace(/ş/g, "s")
    .replace(/ı/g, "i")
    .replace(/ö/g, "o")
    .replace(/ç/g, "c")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function createEmptyModuleDetails(moduleKey) {
  const detailConfig = MODULE_DETAIL_CONFIG[moduleKey];

  if (!detailConfig) {
    return {
      features: {},
      actions: {},
      scope: { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] },
    };
  }

  return {
    features: detailConfig.features.reduce((acc, feature) => {
      acc[feature.key] = false;
      return acc;
    }, {}),
    actions: detailConfig.actions.reduce((acc, action) => {
      acc[action.key] = false;
      return acc;
    }, {}),
    scope: { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] },
  };
}

function createEmptyModules() {
  return ACCESS_MODULES.reduce((acc, module) => {
    acc[module.key] = {
      view: false,
      admin: false,
      details: createEmptyModuleDetails(module.key),
    };
    return acc;
  }, {});
}

function createEmptyUser(email) {
  return {
    email,
    name: email,
    role: "viewer",
    status: "active",
    groups: [],
    modules: createEmptyModules(),
  };
}

function createEmptyGroup(id, name) {
  return {
    id,
    name,
    description: "",
    status: "active",
    modules: createEmptyModules(),
  };
}

function ensureModuleAccess(entity, moduleKey) {
  return entity.modules?.[moduleKey] || {
    view: false,
    admin: false,
    details: createEmptyModuleDetails(moduleKey),
  };
}

function toggleInList(list = [], value) {
  if (list.includes(value)) return list.filter((item) => item !== value);
  return [...list, value];
}

export default function AccessControl() {
  const navigate = useNavigate();
  const { user, accessConfig, updateAccessConfig, isSuperAdmin } = useAuth();

  const [draft, setDraft] = useState(() => clone(accessConfig));
  const [mode, setMode] = useState("users");
  const [selectedEmail, setSelectedEmail] = useState(() => user?.email || "erdi.aydin@yemeksepeti.com");
  const [selectedGroupId, setSelectedGroupId] = useState("construction_team");
  const [selectedModuleKey, setSelectedModuleKey] = useState("dockos");
  const [query, setQuery] = useState("");
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [saved, setSaved] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState("");
  const [passwordReset, setPasswordReset] = useState({ busy: false, error: "", result: null });
  const [passwordCopied, setPasswordCopied] = useState(false);

  const users = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    return Object.values(draft.users || {})
      .filter((item) => {
        if (!normalized || mode !== "users") return true;
        return [item.email, item.name, item.role, item.status, ...(item.groups || [])]
          .join(" ")
          .toLowerCase()
          .includes(normalized);
      })
      .sort((a, b) => a.email.localeCompare(b.email));
  }, [draft, query, mode]);

  const groups = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    return Object.values(draft.groups || {})
      .filter((item) => {
        if (!normalized || mode !== "groups") return true;
        return [item.id, item.name, item.description, item.status]
          .join(" ")
          .toLowerCase()
          .includes(normalized);
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [draft, query, mode]);

  const selectedUser = draft.users?.[selectedEmail] || users[0];
  const selectedGroup = draft.groups?.[selectedGroupId] || groups[0];

  const selectedEntity = mode === "users" ? selectedUser : selectedGroup;
  const selectedDetailConfig = MODULE_DETAIL_CONFIG[selectedModuleKey];
  const selectedModuleAccess = selectedEntity
    ? ensureModuleAccess(selectedEntity, selectedModuleKey)
    : null;

  function updateSelectedEntity(patch) {
    if (!selectedEntity) return;

    if (mode === "users") {
      setDraft((current) => ({
        ...current,
        users: {
          ...current.users,
          [selectedUser.email]: {
            ...current.users[selectedUser.email],
            ...patch,
          },
        },
      }));
      return;
    }

    setDraft((current) => ({
      ...current,
      groups: {
        ...current.groups,
        [selectedGroup.id]: {
          ...current.groups[selectedGroup.id],
          ...patch,
        },
      },
    }));
  }

  function updateModule(moduleKey, key, value) {
    if (!selectedEntity) return;

    const currentAccess = ensureModuleAccess(selectedEntity, moduleKey);

    const nextModules = {
      ...(selectedEntity.modules || {}),
      [moduleKey]: {
        ...currentAccess,
        [key]: value,
      },
    };

    if (key === "admin" && value) {
      nextModules[moduleKey].view = true;
      const detailConfig = MODULE_DETAIL_CONFIG[moduleKey];

      if (detailConfig) {
        nextModules[moduleKey].details = {
          ...(nextModules[moduleKey].details || createEmptyModuleDetails(moduleKey)),
          features: detailConfig.features.reduce((acc, feature) => {
            acc[feature.key] = true;
            return acc;
          }, {}),
          actions: detailConfig.actions.reduce((acc, action) => {
            acc[action.key] = true;
            return acc;
          }, {}),
          scope: {
            ...(nextModules[moduleKey].details?.scope || {}),
            type: nextModules[moduleKey].details?.scope?.type || "all",
          },
        };
      }
    }

    if (key === "view" && !value) {
      nextModules[moduleKey].admin = false;
    }

    updateSelectedEntity({ modules: nextModules });
  }

  function updateDetail(moduleKey, section, key, value) {
    if (!selectedEntity) return;

    const currentAccess = ensureModuleAccess(selectedEntity, moduleKey);
    const currentDetails = currentAccess.details || createEmptyModuleDetails(moduleKey);

    const nextModules = {
      ...(selectedEntity.modules || {}),
      [moduleKey]: {
        ...currentAccess,
        view: true,
        details: {
          ...currentDetails,
          [section]: {
            ...(currentDetails[section] || {}),
            [key]: value,
          },
        },
      },
    };

    updateSelectedEntity({ modules: nextModules });
  }

  function updateScopeType(moduleKey, type) {
    if (!selectedEntity) return;

    const currentAccess = ensureModuleAccess(selectedEntity, moduleKey);
    const currentDetails = currentAccess.details || createEmptyModuleDetails(moduleKey);

    const nextModules = {
      ...(selectedEntity.modules || {}),
      [moduleKey]: {
        ...currentAccess,
        view: true,
        details: {
          ...currentDetails,
          scope: {
            ...(currentDetails.scope || {}),
            type,
          },
        },
      },
    };

    updateSelectedEntity({ modules: nextModules });
  }

  function updateScopeList(moduleKey, listKey, value) {
    if (!selectedEntity) return;

    const currentAccess = ensureModuleAccess(selectedEntity, moduleKey);
    const currentDetails = currentAccess.details || createEmptyModuleDetails(moduleKey);
    const currentScope = currentDetails.scope || {};

    const nextModules = {
      ...(selectedEntity.modules || {}),
      [moduleKey]: {
        ...currentAccess,
        view: true,
        details: {
          ...currentDetails,
          scope: {
            ...currentScope,
            [listKey]: toggleInList(currentScope[listKey] || [], value),
          },
        },
      },
    };

    updateSelectedEntity({ modules: nextModules });
  }

  function addUser() {
    const email = normalizeEmail(newUserEmail);
    if (!email || !email.includes("@")) return;

    setDraft((current) => ({
      ...current,
      users: {
        ...current.users,
        [email]: current.users[email] || createEmptyUser(email),
      },
    }));

    setMode("users");
    setSelectedEmail(email);
    setNewUserEmail("");
  }

  function addGroup() {
    const name = String(newGroupName || "").trim();
    const id = normalizeGroupId(name);

    if (!id || !name) return;

    setDraft((current) => ({
      ...current,
      groups: {
        ...current.groups,
        [id]: current.groups[id] || createEmptyGroup(id, name),
      },
    }));

    setMode("groups");
    setSelectedGroupId(id);
    setNewGroupName("");
  }

  function duplicateEntity() {
    if (!selectedEntity) return;

    if (mode === "users") {
      const email = normalizeEmail(window.prompt("Yeni kullanıcının e-posta adresi:"));
      if (!email || !email.includes("@")) return;

      setDraft((current) => ({
        ...current,
        users: {
          ...current.users,
          [email]: { ...clone(selectedUser), email, name: email, role: "viewer" },
        },
      }));

      setSelectedEmail(email);
      return;
    }

    const name = String(window.prompt("Yeni grup adı:") || "").trim();
    const id = normalizeGroupId(name);
    if (!id || !name) return;

    setDraft((current) => ({
      ...current,
      groups: {
        ...current.groups,
        [id]: { ...clone(selectedGroup), id, name },
      },
    }));

    setSelectedGroupId(id);
  }

  function removeEntity() {
    if (!selectedEntity) return;

    if (mode === "users") {
      if (selectedUser.role === "super_admin") {
        window.alert("Super Admin kullanıcısı silinemez.");
        return;
      }

      const ok = window.confirm(`${selectedUser.email} silinsin mi?`);
      if (!ok) return;

      setDraft((current) => {
        const next = clone(current);
        delete next.users[selectedUser.email];
        return next;
      });

      setSelectedEmail("erdi.aydin@yemeksepeti.com");
      return;
    }

    if (selectedGroup.id === "super_admins") {
      window.alert("Super Admins grubu silinemez.");
      return;
    }

    const ok = window.confirm(`${selectedGroup.name} grubu silinsin mi?`);
    if (!ok) return;

    setDraft((current) => {
      const next = clone(current);
      delete next.groups[selectedGroup.id];

      Object.values(next.users || {}).forEach((item) => {
        item.groups = (item.groups || []).filter((groupId) => groupId !== selectedGroup.id);
      });

      return next;
    });

    setSelectedGroupId("construction_team");
  }

  function toggleUserGroup(groupId) {
    if (!selectedUser) return;

    updateSelectedEntity({
      groups: toggleInList(selectedUser.groups || [], groupId),
    });
  }

  function saveChanges() {
    updateAccessConfig(draft);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  }

  function refreshModules() {
    const next = refreshAccessConfig(draft);
    const changed = JSON.stringify(next) !== JSON.stringify(draft);

    setDraft(next);
    updateAccessConfig(next);
    setRefreshNotice(
      changed
        ? "Eksik platform ve yetki alanları eklendi; mevcut seçimler korundu."
        : "Platform ve yetki kataloğu zaten güncel."
    );
    window.setTimeout(() => setRefreshNotice(""), 3200);
  }

  async function resetSelectedPassword() {
    if (!selectedUser?.email || passwordReset.busy) return;
    const confirmed = window.confirm(
      `${selectedUser.email} için geçici parola üretilecek. Kullanıcının açık oturumları kapatılacak. Devam edilsin mi?`
    );
    if (!confirmed) return;

    setPasswordReset({ busy: true, error: "", result: null });
    setPasswordCopied(false);
    try {
      const result = await apiPost("/identity/admin/users/password-reset", {
        username: selectedUser.email,
      });
      setPasswordReset({ busy: false, error: "", result });
    } catch (error) {
      setPasswordReset({
        busy: false,
        error: error.message || "Parola sıfırlanamadı.",
        result: null,
      });
    }
  }

  async function copyTemporaryPassword() {
    const value = passwordReset.result?.temporary_password;
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setPasswordCopied(true);
    window.setTimeout(() => setPasswordCopied(false), 1800);
  }

  function selectUser(email) {
    setSelectedEmail(email);
    setPasswordReset({ busy: false, error: "", result: null });
    setPasswordCopied(false);
  }

  function resetToDefault() {
    const ok = window.confirm("Tüm kullanıcı ve grup yetkileri varsayılan yapıya dönsün mü?");
    if (!ok) return;

    const next = clone(DEFAULT_ACCESS_CONFIG);
    setDraft(next);
    setSelectedEmail("erdi.aydin@yemeksepeti.com");
    setSelectedGroupId("construction_team");
    updateAccessConfig(next);
  }

  if (!isSuperAdmin()) {
    return (
      <main className="access-page">
        <section className="access-denied">
          <Lock size={32} />
          <h1>Bu alan yalnızca Super Admin için.</h1>
          <button onClick={() => navigate("/")}>Ana ekrana dön</button>
        </section>
      </main>
    );
  }

  return (
    <main className="access-page">
      <div className="access-bg-grid" />
      <div className="access-orb orb-a" />
      <div className="access-orb orb-b" />

      <section className="access-shell">
        <header className="access-topbar">
          <button className="access-back" onClick={() => navigate("/")}>
            <ArrowLeft size={18} />
            Control Center
          </button>

          <div className="access-admin-pill">
            <ShieldCheck size={16} />
            Super Admin Mode
          </div>
        </header>

        <section className="access-hero">
          <motion.div
            initial={{ opacity: 0, y: 22, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.58, ease: [0.16, 0.86, 0.22, 1] }}
          >
            <span>Access Control</span>
            <h1>Kullanıcı ve grup yetkilerini yönet.</h1>
            <p>
              Kullanıcı bazlı istisnaları ve ekip/grup bazlı erişimleri tek merkezden kontrol et.
            </p>
          </motion.div>

          <motion.div
            className="access-summary"
            initial={{ opacity: 0, y: 22, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.58, delay: 0.12, ease: [0.16, 0.86, 0.22, 1] }}
          >
            <div>
              <small>Kullanıcı</small>
              <strong>{Object.keys(draft.users || {}).length}</strong>
            </div>

            <div>
              <small>Grup</small>
              <strong>{Object.keys(draft.groups || {}).length}</strong>
            </div>

            <div>
              <small>Modül</small>
              <strong>{ACCESS_MODULES.length}</strong>
            </div>
          </motion.div>
        </section>

        <div className="access-control-toolbar">
          <div className="access-mode-tabs">
            <button className={mode === "users" ? "active" : ""} onClick={() => setMode("users")}>
              <UserRound size={17} />
              Kullanıcılar
            </button>
            <button className={mode === "groups" ? "active" : ""} onClick={() => setMode("groups")}>
              <UsersRound size={17} />
              Gruplar
            </button>
          </div>

          <div className="access-refresh-area">
            <span className="access-refresh-notice" aria-live="polite">{refreshNotice}</span>
            <button type="button" className="access-refresh-btn" onClick={refreshModules}>
              <RefreshCw size={16} />
              Modülleri Yenile
            </button>
          </div>
        </div>

        <section className="access-grid access-grid-v2">
          <motion.aside
            className="access-users"
            initial={{ opacity: 0, x: -22, filter: "blur(10px)" }}
            animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.58, delay: 0.16, ease: [0.16, 0.86, 0.22, 1] }}
          >
            <div className="access-search">
              <Search size={17} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={mode === "users" ? "Kullanıcı ara..." : "Grup ara..."}
              />
            </div>

            {mode === "users" ? (
              <div className="access-add-user">
                <input
                  value={newUserEmail}
                  onChange={(e) => setNewUserEmail(e.target.value)}
                  placeholder="yeni.kullanici@yemeksepeti.com"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") addUser();
                  }}
                />
                <button onClick={addUser}>
                  <Plus size={17} />
                </button>
              </div>
            ) : (
              <div className="access-add-user">
                <input
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="Yeni grup adı"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") addGroup();
                  }}
                />
                <button onClick={addGroup}>
                  <Plus size={17} />
                </button>
              </div>
            )}

            <div className="access-user-list">
              {mode === "users"
                ? users.map((item) => (
                    <button
                      key={item.email}
                      className={item.email === selectedUser?.email ? "active" : ""}
                      onClick={() => selectUser(item.email)}
                    >
                      <UserRound size={17} />
                      <div>
                        <strong>{item.name || item.email}</strong>
                        <span>{item.email}</span>
                      </div>
                      <small>{item.role}</small>
                    </button>
                  ))
                : groups.map((item) => (
                    <button
                      key={item.id}
                      className={item.id === selectedGroup?.id ? "active" : ""}
                      onClick={() => setSelectedGroupId(item.id)}
                    >
                      <UsersRound size={17} />
                      <div>
                        <strong>{item.name}</strong>
                        <span>{item.description || item.id}</span>
                      </div>
                      <small>{item.status}</small>
                    </button>
                  ))}
            </div>
          </motion.aside>

          <motion.section
            className="access-editor"
            initial={{ opacity: 0, x: 22, filter: "blur(10px)" }}
            animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.58, delay: 0.22, ease: [0.16, 0.86, 0.22, 1] }}
          >
            {selectedEntity ? (
              <>
                <div className="access-editor-head">
                  <div>
                    <span>{mode === "users" ? "Selected User" : "Selected Group"}</span>
                    <h2>{mode === "users" ? selectedUser.email : selectedGroup.name}</h2>
                  </div>

                  <div className="access-editor-actions">
                    {mode === "users" ? (
                      <button onClick={resetSelectedPassword} disabled={passwordReset.busy}>
                        <KeyRound size={16} />
                        {passwordReset.busy ? "Sıfırlanıyor" : "Şifre sıfırla"}
                      </button>
                    ) : null}

                    <button onClick={duplicateEntity}>
                      <Copy size={16} />
                      Kopyala
                    </button>

                    <button className="danger" onClick={removeEntity}>
                      <Trash2 size={16} />
                      Sil
                    </button>
                  </div>
                </div>

                {mode === "users" ? (
                  <>
                    <div className="access-profile">
                      <label>
                        Ad
                        <input
                          value={selectedUser.name || ""}
                          onChange={(e) => updateSelectedEntity({ name: e.target.value })}
                        />
                      </label>

                      <label>
                        Rol
                        <select
                          value={selectedUser.role}
                          onChange={(e) => updateSelectedEntity({ role: e.target.value })}
                        >
                          <option value="super_admin">super_admin</option>
                          <option value="admin">admin</option>
                          <option value="module_admin">module_admin</option>
                          <option value="viewer">viewer</option>
                        </select>
                      </label>

                      <label>
                        Durum
                        <select
                          value={selectedUser.status}
                          onChange={(e) => updateSelectedEntity({ status: e.target.value })}
                        >
                          <option value="active">active</option>
                          <option value="passive">passive</option>
                        </select>
                      </label>
                    </div>

                    <div className="access-group-box">
                      <h4>Kullanıcı Grupları</h4>
                      <div>
                        {Object.values(draft.groups || {}).map((group) => (
                          <label key={group.id}>
                            <input
                              type="checkbox"
                              checked={(selectedUser.groups || []).includes(group.id)}
                              disabled={selectedUser.role === "super_admin" && group.id === "super_admins"}
                              onChange={() => toggleUserGroup(group.id)}
                            />
                            <span>{group.name}</span>
                          </label>
                        ))}
                      </div>
                    </div>

                    <section className="access-password-reset" aria-live="polite">
                      <div>
                        <KeyRound size={19} />
                        <span>
                          <strong>Güvenli parola sıfırlama</strong>
                          <small>
                            Geçici parola yalnızca bir kez gösterilir. Eski oturumlar iptal edilir ve kullanıcı ilk girişte yeni parola belirler.
                          </small>
                        </span>
                      </div>

                      {passwordReset.error ? (
                        <p className="access-password-error">{passwordReset.error}</p>
                      ) : null}

                      {passwordReset.result ? (
                        <div className="access-temporary-password">
                          <label>
                            Tek kullanımlık geçici parola
                            <input
                              readOnly
                              value={passwordReset.result.temporary_password || ""}
                              onFocus={(event) => event.currentTarget.select()}
                            />
                          </label>
                          <button type="button" onClick={copyTemporaryPassword}>
                            {passwordCopied ? <Check size={16} /> : <Copy size={16} />}
                            {passwordCopied ? "Kopyalandı" : "Kopyala"}
                          </button>
                        </div>
                      ) : null}
                    </section>
                  </>
                ) : (
                  <div className="access-profile access-profile-group">
                    <label>
                      Grup Adı
                      <input
                        value={selectedGroup.name || ""}
                        onChange={(e) => updateSelectedEntity({ name: e.target.value })}
                      />
                    </label>

                    <label>
                      Açıklama
                      <input
                        value={selectedGroup.description || ""}
                        onChange={(e) => updateSelectedEntity({ description: e.target.value })}
                      />
                    </label>

                    <label>
                      Durum
                      <select
                        value={selectedGroup.status}
                        onChange={(e) => updateSelectedEntity({ status: e.target.value })}
                      >
                        <option value="active">active</option>
                        <option value="passive">passive</option>
                      </select>
                    </label>
                  </div>
                )}

                <div className="access-module-table">
                  <div className="access-table-head access-table-head-v2">
                    <span>Modül</span>
                    <span>View</span>
                    <span>Admin</span>
                    <span>Detay</span>
                  </div>

                  {ACCESS_MODULES.map((module) => {
                    const moduleAccess = ensureModuleAccess(selectedEntity, module.key);
                    const hasDetail = Boolean(MODULE_DETAIL_CONFIG[module.key]);

                    return (
                      <div className="access-module-row access-module-row-v2" key={module.key}>
                        <div>
                          <strong>{module.title}</strong>
                          <small>{module.description}</small>
                        </div>

                        <label className="access-switch">
                          <input
                            type="checkbox"
                            checked={Boolean(moduleAccess.view)}
                            disabled={mode === "users" && selectedUser.role === "super_admin"}
                            onChange={(e) => updateModule(module.key, "view", e.target.checked)}
                          />
                          <span />
                        </label>

                        <label className="access-switch">
                          <input
                            type="checkbox"
                            checked={Boolean(moduleAccess.admin)}
                            disabled={mode === "users" && selectedUser.role === "super_admin"}
                            onChange={(e) => updateModule(module.key, "admin", e.target.checked)}
                          />
                          <span />
                        </label>

                        <button
                          type="button"
                          className={`access-detail-btn ${selectedModuleKey === module.key ? "active" : ""}`}
                          disabled={!hasDetail}
                          onClick={() => {
                            if (hasDetail) setSelectedModuleKey(module.key);
                          }}
                        >
                          <SlidersHorizontal size={15} />
                          Detay
                          <ChevronRight size={15} />
                        </button>
                      </div>
                    );
                  })}
                </div>

                <footer className="access-footer">
                  <button className="ghost" onClick={resetToDefault}>
                    <RotateCcw size={17} />
                    Varsayılan
                  </button>

                  <button className="save" onClick={saveChanges}>
                    {saved ? <Check size={17} /> : <Save size={17} />}
                    {saved ? "Kaydedildi" : "Kaydet"}
                  </button>
                </footer>
              </>
            ) : (
              <div className="access-empty">
                <UsersRound size={30} />
                <strong>Seçim yapılmadı.</strong>
              </div>
            )}
          </motion.section>

          <motion.aside
            className="access-detail-panel"
            initial={{ opacity: 0, x: 24, filter: "blur(10px)" }}
            animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.58, delay: 0.28, ease: [0.16, 0.86, 0.22, 1] }}
          >
            {selectedDetailConfig && selectedModuleAccess ? (
              <>
                <div className="access-detail-head">
                  <span>{mode === "users" ? "User Detail" : "Group Detail"}</span>
                  <h3>{selectedDetailConfig.title}</h3>
                  <p>
                    {mode === "users"
                      ? "Kullanıcıya özel istisna yetkileri. Grup yetkileriyle birleşerek çalışır."
                      : "Bu gruba üye olan tüm kullanıcıların kazanacağı ortak yetkiler."}
                  </p>
                </div>

                <div className="access-detail-section">
                  <h4>Ekranlar</h4>

                  {selectedDetailConfig.features.map((feature) => (
                    <label className="access-detail-check" key={feature.key}>
                      <input
                        type="checkbox"
                        checked={Boolean(selectedModuleAccess.details?.features?.[feature.key])}
                        disabled={mode === "users" && selectedUser?.role === "super_admin"}
                        onChange={(e) =>
                          updateDetail(selectedModuleKey, "features", feature.key, e.target.checked)
                        }
                      />
                      <div>
                        <strong>{feature.label}</strong>
                        <span>{feature.description}</span>
                      </div>
                    </label>
                  ))}
                </div>

                <div className="access-detail-section">
                  <h4>Aksiyonlar</h4>

                  <div className="access-action-grid">
                    {selectedDetailConfig.actions.map((action) => (
                      <label className="access-action-chip" key={action.key}>
                        <input
                          type="checkbox"
                          checked={Boolean(selectedModuleAccess.details?.actions?.[action.key])}
                          disabled={mode === "users" && selectedUser?.role === "super_admin"}
                          onChange={(e) =>
                            updateDetail(selectedModuleKey, "actions", action.key, e.target.checked)
                          }
                        />
                        <span>{action.label}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="access-detail-section">
                  <h4>Veri Kapsamı</h4>

                  <select
                    className="access-scope-select"
                    value={selectedModuleAccess.details?.scope?.type || "all"}
                    disabled={mode === "users" && selectedUser?.role === "super_admin"}
                    onChange={(e) => updateScopeType(selectedModuleKey, e.target.value)}
                  >
                    {selectedDetailConfig.scope.types.map((scopeType) => (
                      <option key={scopeType.key} value={scopeType.key}>
                        {scopeType.label}
                      </option>
                    ))}
                  </select>

                  {selectedModuleAccess.details?.scope?.type === "region" ? (
                    <ScopeList
                      title="Bölgeler"
                      options={SCOPE_OPTIONS.regions}
                      selected={selectedModuleAccess.details?.scope?.regions || []}
                      onToggle={(value) => updateScopeList(selectedModuleKey, "regions", value)}
                      disabled={mode === "users" && selectedUser?.role === "super_admin"}
                    />
                  ) : null}

                  {selectedModuleAccess.details?.scope?.type === "warehouse" ? (
                    <ScopeList
                      title="Depolar"
                      options={SCOPE_OPTIONS.warehouses}
                      selected={selectedModuleAccess.details?.scope?.warehouses || []}
                      onToggle={(value) => updateScopeList(selectedModuleKey, "warehouses", value)}
                      disabled={mode === "users" && selectedUser?.role === "super_admin"}
                    />
                  ) : null}

                  {selectedModuleAccess.details?.scope?.type === "supplier" ? (
                    <ScopeList
                      title="Tedarikçiler"
                      options={SCOPE_OPTIONS.suppliers}
                      selected={selectedModuleAccess.details?.scope?.suppliers || []}
                      onToggle={(value) => updateScopeList(selectedModuleKey, "suppliers", value)}
                      disabled={mode === "users" && selectedUser?.role === "super_admin"}
                    />
                  ) : null}

                  {selectedModuleAccess.details?.scope?.type === "cost_center" ? (
                    <ScopeList
                      title="Cost Center"
                      options={SCOPE_OPTIONS.costCenters}
                      selected={selectedModuleAccess.details?.scope?.costCenters || []}
                      onToggle={(value) => updateScopeList(selectedModuleKey, "costCenters", value)}
                      disabled={mode === "users" && selectedUser?.role === "super_admin"}
                    />
                  ) : null}
                </div>
              </>
            ) : (
              <div className="access-detail-empty">
                <SlidersHorizontal size={28} />
                <strong>Bu modül için detay yetki yok.</strong>
              </div>
            )}
          </motion.aside>
        </section>
      </section>
    </main>
  );
}

function ScopeList({ title, options, selected, onToggle, disabled }) {
  return (
    <div className="access-scope-list">
      <strong>{title}</strong>

      <div>
        {options.map((option) => (
          <label key={option}>
            <input
              type="checkbox"
              checked={selected.includes(option)}
              disabled={disabled}
              onChange={() => onToggle(option)}
            />
            <span>{option}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
