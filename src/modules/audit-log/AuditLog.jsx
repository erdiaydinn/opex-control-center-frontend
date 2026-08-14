import React, { useEffect, useMemo, useState } from "react";
import { fetchAuditEvents } from "./auditLogApi";
import { useAuth } from "../../auth/AuthContext.jsx";
import "./audit-log.css";

function formatDate(value) {
  if (!value) return "-";

  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

function decisionLabel(decision) {
  const labels = {
    allowed: "İzin verildi",
    denied: "Reddedildi",
    error: "Hata",
  };

  return labels[decision] || decision;
}

export default function AuditLog() {
  const { getAccessToken } = useAuth();
  const [items, setItems] = useState([]);
  const [actor, setActor] = useState("");
  const [decision, setDecision] = useState("");
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadEvents() {
    setLoading(true);
    setError("");

    try {
      const result = await fetchAuditEvents({
        limit: 100,
        actor,
        decision,
        action,
        accessToken: getAccessToken(),
      });

      setItems(result?.items || []);
    } catch (err) {
      setError(err.message || "Audit kayıtları alınamadı.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadEvents();
  }, []);

  const summary = useMemo(() => {
    return items.reduce(
      (acc, item) => {
        acc.total += 1;
        acc[item.decision] = (acc[item.decision] || 0) + 1;
        return acc;
      },
      {
        total: 0,
        allowed: 0,
        denied: 0,
        error: 0,
      },
    );
  }, [items]);

  function handleSubmit(event) {
    event.preventDefault();
    loadEvents();
  }

  function handleReset() {
    setActor("");
    setDecision("");
    setAction("");

    setTimeout(() => {
      loadEvents();
    }, 0);
  }

  return (
    <section className="audit-log">
      <header className="audit-log__header">
        <div>
          <span className="audit-log__eyebrow">Platform Çekirdeği</span>
          <h1>Audit Log</h1>
          <p>
            İzin verilen, reddedilen ve hataya düşen platform işlemlerini
            tenant bağlamında izleyin.
          </p>
        </div>

        <button
          className="audit-log__refresh"
          type="button"
          onClick={loadEvents}
          disabled={loading}
        >
          {loading ? "Yükleniyor..." : "Yenile"}
        </button>
      </header>

      <div className="audit-log__summary">
        <article>
          <span>Toplam</span>
          <strong>{summary.total}</strong>
        </article>
        <article>
          <span>İzin verilen</span>
          <strong>{summary.allowed}</strong>
        </article>
        <article>
          <span>Reddedilen</span>
          <strong>{summary.denied}</strong>
        </article>
        <article>
          <span>Hata</span>
          <strong>{summary.error}</strong>
        </article>
      </div>

      <form className="audit-log__filters" onSubmit={handleSubmit}>
        <label>
          Aktör
          <input
            value={actor}
            onChange={(event) => setActor(event.target.value)}
            placeholder="erdi"
          />
        </label>

        <label>
          Karar
          <select
            value={decision}
            onChange={(event) => setDecision(event.target.value)}
          >
            <option value="">Tümü</option>
            <option value="allowed">İzin verildi</option>
            <option value="denied">Reddedildi</option>
            <option value="error">Hata</option>
          </select>
        </label>

        <label>
          Aksiyon
          <input
            value={action}
            onChange={(event) => setAction(event.target.value)}
            placeholder="get:/v1/context"
          />
        </label>

        <div className="audit-log__filter-actions">
          <button type="submit">Filtrele</button>
          <button type="button" onClick={handleReset}>
            Temizle
          </button>
        </div>
      </form>

      {error && <div className="audit-log__error">{error}</div>}

      <div className="audit-log__table-wrap">
        <table className="audit-log__table">
          <thead>
            <tr>
              <th>Zaman</th>
              <th>Aktör</th>
              <th>Aksiyon</th>
              <th>Karar</th>
              <th>Durum</th>
              <th>Request ID</th>
            </tr>
          </thead>
          <tbody>
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan="6" className="audit-log__empty">
                  Kayıt bulunamadı.
                </td>
              </tr>
            )}

            {items.map((item) => (
              <tr key={item.id}>
                <td>{formatDate(item.created_at)}</td>
                <td>{item.actor}</td>
                <td>
                  <code>{item.action}</code>
                </td>
                <td>
                  <span
                    className={`audit-log__decision audit-log__decision--${item.decision}`}
                  >
                    {decisionLabel(item.decision)}
                  </span>
                </td>
                <td>{item.data?.status_code ?? "-"}</td>
                <td>
                  <code title={item.request_id}>
                    {item.request_id?.slice(0, 12)}...
                  </code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
