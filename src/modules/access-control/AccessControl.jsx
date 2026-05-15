import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Copy,
  Lock,
  Plus,
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
import {
  ACCESS_MODULES,
  DEFAULT_ACCESS_CONFIG,
  MODULE_DETAIL_CONFIG,
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

function createEmptyModuleDetails(moduleKey) {
  const detailConfig = MODULE_DETAIL_CONFIG[moduleKey];

  if (!detailConfig) {
    return {
      features: {},
      actions: {},
      scope: {
        type: "all",
        regions: [],
        warehouses: [],
        suppliers: [],
        costCenters: [],
      },
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
    scope: {
      type: "all",
      regions: [],
      warehouses: [],
      suppliers: [],
      costCenters: [],
    },
  };
}

function createEmptyUser(email) {
  const modules = ACCESS_MODULES.reduce((acc, module) => {
    acc[module.key] = {
      view: false,
      admin: false,
      details: createEmptyModuleDetails(module.key),
    };
    return acc;
  }, {});

  return {
    email,
    name: email,
    role: "viewer",
    status: "active",
    modules,
  };
}

function ensureModuleAccess(user, moduleKey) {
  return user.modules?.[moduleKey] || {
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
  const [selectedEmail, setSelectedEmail] = useState(() => user?.email || "erdi.aydin@yemeksepeti.com");
  const [selectedModuleKey, setSelectedModuleKey] = useState("dockos");
  const [query, setQuery] = useState("");
  const [newUserEmail, setNewUserEmail] = useState("");
  const [saved, setSaved] = useState(false);

  const users = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    return Object.values(draft.users || {})
      .filter((item) => {
        if (!normalized) return true;
        return [item.email, item.name, item.role, item.status]
          .join(" ")
          .toLowerCase()
          .includes(normalized);
      })
      .sort((a, b) => a.email.localeCompare(b.email));
  }, [draft, query]);

  const selectedUser = draft.users?.[selectedEmail] || users[0];
  const selectedDetailConfig = MODULE_DETAIL_CONFIG[selectedModuleKey];
  const selectedModuleAccess = selectedUser
    ? ensureModuleAccess(selectedUser, selectedModuleKey)
    : null;

  function updateSelectedUser(patch) {
    if (!selectedUser) return;

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
  }

  function updateModule(moduleKey, key, value) {
    if (!selectedUser) return;

    const currentAccess = ensureModuleAccess(selectedUser, moduleKey);

    const nextModules = {
      ...(selectedUser.modules || {}),
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

    updateSelectedUser({ modules: nextModules });
  }

  function updateDetail(moduleKey, section, key, value) {
    if (!selectedUser) return;

    const currentAccess = ensureModuleAccess(selectedUser, moduleKey);
    const currentDetails = currentAccess.details || createEmptyModuleDetails(moduleKey);

    const nextModules = {
      ...(selectedUser.modules || {}),
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

    updateSelectedUser({ modules: nextModules });
  }

  function updateScopeType(moduleKey, type) {
    if (!selectedUser) return;

    const currentAccess = ensureModuleAccess(selectedUser, moduleKey);
    const currentDetails = currentAccess.details || createEmptyModuleDetails(moduleKey);

    const nextModules = {
      ...(selectedUser.modules || {}),
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

    updateSelectedUser({ modules: nextModules });
  }

  function updateScopeList(moduleKey, listKey, value) {
    if (!selectedUser) return;

    const currentAccess = ensureModuleAccess(selectedUser, moduleKey);
    const currentDetails = currentAccess.details || createEmptyModuleDetails(moduleKey);
    const currentScope = currentDetails.scope || {};

    const nextModules = {
      ...(selectedUser.modules || {}),
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

    updateSelectedUser({ modules: nextModules });
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

    setSelectedEmail(email);
    setNewUserEmail("");
  }

  function duplicateUser() {
    if (!selectedUser) return;

    const email = normalizeEmail(window.prompt("Yeni kullanıcının e-posta adresi:"));

    if (!email || !email.includes("@")) return;

    setDraft((current) => ({
      ...current,
      users: {
        ...current.users,
        [email]: {
          ...clone(selectedUser),
          email,
          name: email,
          role: "viewer",
        },
      },
    }));

    setSelectedEmail(email);
  }

  function removeUser() {
    if (!selectedUser) return;

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
  }

  function saveChanges() {
    updateAccessConfig(draft);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  }

  function resetToDefault() {
    const ok = window.confirm("Tüm yetkiler varsayılan demo yapısına dönsün mü?");
    if (!ok) return;

    const next = clone(DEFAULT_ACCESS_CONFIG);
    setDraft(next);
    setSelectedEmail("erdi.aydin@yemeksepeti.com");
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
            <h1>Kim neyi, hangi kapsamda görecek?</h1>
            <p>
              Modül kapısını, modül içi ekranları, aksiyonları ve veri kapsamını tek yerden yönet.
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
              <small>Modül</small>
              <strong>{ACCESS_MODULES.length}</strong>
            </div>

            <div>
              <small>Aktif</small>
              <strong>
                {Object.values(draft.users || {}).filter((item) => item.status === "active").length}
              </strong>
            </div>
          </motion.div>
        </section>

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
                placeholder="Kullanıcı ara..."
              />
            </div>

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

            <div className="access-user-list">
              {users.map((item) => (
                <button
                  key={item.email}
                  className={item.email === selectedUser?.email ? "active" : ""}
                  onClick={() => setSelectedEmail(item.email)}
                >
                  <UserRound size={17} />
                  <div>
                    <strong>{item.name || item.email}</strong>
                    <span>{item.email}</span>
                  </div>
                  <small>{item.role}</small>
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
            {selectedUser ? (
              <>
                <div className="access-editor-head">
                  <div>
                    <span>Selected User</span>
                    <h2>{selectedUser.email}</h2>
                  </div>

                  <div className="access-editor-actions">
                    <button onClick={duplicateUser}>
                      <Copy size={16} />
                      Kopyala
                    </button>

                    <button className="danger" onClick={removeUser}>
                      <Trash2 size={16} />
                      Sil
                    </button>
                  </div>
                </div>

                <div className="access-profile">
                  <label>
                    Ad
                    <input
                      value={selectedUser.name || ""}
                      onChange={(e) => updateSelectedUser({ name: e.target.value })}
                    />
                  </label>

                  <label>
                    Rol
                    <select
                      value={selectedUser.role}
                      onChange={(e) => updateSelectedUser({ role: e.target.value })}
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
                      onChange={(e) => updateSelectedUser({ status: e.target.value })}
                    >
                      <option value="active">active</option>
                      <option value="passive">passive</option>
                    </select>
                  </label>
                </div>

                <div className="access-module-table">
                  <div className="access-table-head access-table-head-v2">
                    <span>Modül</span>
                    <span>View</span>
                    <span>Admin</span>
                    <span>Detay</span>
                  </div>

                  {ACCESS_MODULES.map((module) => {
                    const moduleAccess = ensureModuleAccess(selectedUser, module.key);
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
                            disabled={selectedUser.role === "super_admin"}
                            onChange={(e) => updateModule(module.key, "view", e.target.checked)}
                          />
                          <span />
                        </label>

                        <label className="access-switch">
                          <input
                            type="checkbox"
                            checked={Boolean(moduleAccess.admin)}
                            disabled={selectedUser.role === "super_admin"}
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
                <strong>Kullanıcı seçilmedi.</strong>
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
                  <span>Module Detail</span>
                  <h3>{selectedDetailConfig.title}</h3>
                  <p>
                    Bu alan, modül içindeki ekranları, aksiyonları ve veri kapsamını belirler.
                  </p>
                </div>

                <div className="access-detail-section">
                  <h4>Ekranlar</h4>

                  {selectedDetailConfig.features.map((feature) => (
                    <label className="access-detail-check" key={feature.key}>
                      <input
                        type="checkbox"
                        checked={Boolean(selectedModuleAccess.details?.features?.[feature.key])}
                        disabled={selectedUser?.role === "super_admin"}
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
                          disabled={selectedUser?.role === "super_admin"}
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
                    disabled={selectedUser?.role === "super_admin"}
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
                      disabled={selectedUser?.role === "super_admin"}
                    />
                  ) : null}

                  {selectedModuleAccess.details?.scope?.type === "warehouse" ? (
                    <ScopeList
                      title="Depolar"
                      options={SCOPE_OPTIONS.warehouses}
                      selected={selectedModuleAccess.details?.scope?.warehouses || []}
                      onToggle={(value) => updateScopeList(selectedModuleKey, "warehouses", value)}
                      disabled={selectedUser?.role === "super_admin"}
                    />
                  ) : null}

                  {selectedModuleAccess.details?.scope?.type === "supplier" ? (
                    <ScopeList
                      title="Tedarikçiler"
                      options={SCOPE_OPTIONS.suppliers}
                      selected={selectedModuleAccess.details?.scope?.suppliers || []}
                      onToggle={(value) => updateScopeList(selectedModuleKey, "suppliers", value)}
                      disabled={selectedUser?.role === "super_admin"}
                    />
                  ) : null}

                  {selectedModuleAccess.details?.scope?.type === "cost_center" ? (
                    <ScopeList
                      title="Cost Center"
                      options={SCOPE_OPTIONS.costCenters}
                      selected={selectedModuleAccess.details?.scope?.costCenters || []}
                      onToggle={(value) => updateScopeList(selectedModuleKey, "costCenters", value)}
                      disabled={selectedUser?.role === "super_admin"}
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
