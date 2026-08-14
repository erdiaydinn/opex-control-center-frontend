import React, { useCallback, useEffect, useState } from "react";
import { Activity, ArrowLeft, Database, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext.jsx";
import { apiFetch } from "../../api/client.js";
import "./platform-health.css";

function StatusCard({ title, status, detail, icon: Icon, successLabel = "Çalışıyor" }) {
  const healthy = status === "ok";

  return (
    <article className={`platform-health-card ${healthy ? "healthy" : "unhealthy"}`}>
      <div className="platform-health-card-icon">
        <Icon size={22} />
      </div>

      <div>
        <span>{title}</span>
        <strong>{healthy ? successLabel : "Sorun Var"}</strong>
        {detail ? <small>{detail}</small> : null}
      </div>
    </article>
  );
}

export default function PlatformHealth() {
  const navigate = useNavigate();
  const { isSuperAdmin } = useAuth();

  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadHealth = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const result = await apiFetch(
        "/v1/platform/health",
        {
          method: "GET",
        }
      );


      setHealth(result);
    } catch (err) {
      setHealth(null);
      setError(err.message || "Platform sağlık bilgisi alınamadı.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSuperAdmin()) {
      loadHealth();
    } else {
      setLoading(false);
    }
  }, [isSuperAdmin, loadHealth]);

  if (!isSuperAdmin()) {
    return (
      <main className="platform-health-page">
        <section className="platform-health-denied">
          <ShieldCheck size={42} />
          <h1>Erişim reddedildi</h1>
          <p>Platform Health yalnızca Super Admin kullanıcılarına açıktır.</p>
          <button type="button" onClick={() => navigate("/")}>
            Ana ekrana dön
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="platform-health-page">
      <header className="platform-health-header">
        <div>
          <button
            type="button"
            className="platform-health-back"
            onClick={() => navigate("/")}
          >
            <ArrowLeft size={18} />
            Ana ekran
          </button>

          <p>Platform Core</p>
          <h1>Platform Health</h1>
          <span>
            Kritik servislerin sağlık durumunu tek merkezden izle.
          </span>
        </div>

        <button
          type="button"
          className="platform-health-refresh"
          onClick={loadHealth}
          disabled={loading}
        >
          <RefreshCw size={18} className={loading ? "spinning" : ""} />
          {loading ? "Kontrol ediliyor" : "Yenile"}
        </button>
      </header>

      {error ? (
        <section className="platform-health-error">
          <strong>Sağlık bilgisi alınamadı</strong>
          <span>{error}</span>
        </section>
      ) : null}

      {health ? (
        <>
          <section className={`platform-health-summary ${health.status}`}>
            <Activity size={24} />
            <div>
              <strong>
                {health.status === "healthy"
                  ? "Platform sağlıklı"
                  : "Platform kısmen çalışıyor"}
              </strong>
              <span>
                Ortam: {health.environment} · Versiyon: {health.version}
              </span>
            </div>
          </section>

          <section className="platform-health-grid">
            <StatusCard
              title="Core API"
              status={health.checks?.api?.status}
              detail={`Versiyon ${health.checks?.api?.version || "-"}`}
              icon={Server}
            />

            <StatusCard
              title="PostgreSQL"
              status={health.checks?.database?.status}
              detail="Ana platform veritabanı"
              icon={Database}
            />

            <StatusCard
              title="Redis"
              status={health.checks?.redis?.status}
              detail="Önbellek ve geçici işlem servisi"
              icon={Activity}
            />

            <StatusCard
              title="Container Servisleri"
              status={health.checks?.containers?.status}
              detail={`${health.checks?.containers?.summary?.running || 0} çalışıyor · ${health.checks?.containers?.summary?.stopped || 0} durmuş`}
              icon={Server}
            />

            <StatusCard
              title="Veritabanı Yedeği"
              status={health.checks?.backup?.status}
              successLabel="Başarılı"
              detail={
                health.checks?.backup?.details?.completed_at
                  ? `Son yedek: ${new Date(
                      health.checks.backup.details.completed_at
                    ).toLocaleString("tr-TR")}`
                  : "Henüz yedek bilgisi yok"
              }
              icon={Database}
            />
          </section>

          <section className="platform-health-backup">
            <div className="platform-health-section-title">
              <div>
                <p>Data Protection</p>
                <h2>Son Veritabanı Yedeği</h2>
              </div>

              <span>
                {health.checks?.backup?.details?.status === "success"
                  ? "Başarılı"
                  : "Kontrol gerekli"}
              </span>
            </div>

            <div className="platform-health-backup-grid">
              <div>
                <span>Tamamlanma zamanı</span>
                <strong>
                  {health.checks?.backup?.details?.completed_at
                    ? new Date(
                        health.checks.backup.details.completed_at
                      ).toLocaleString("tr-TR")
                    : "-"}
                </strong>
              </div>

              <div>
                <span>Dosya</span>
                <strong>
                  {health.checks?.backup?.details?.filename || "-"}
                </strong>
              </div>

              <div>
                <span>Boyut</span>
                <strong>
                  {health.checks?.backup?.details?.size_bytes
                    ? `${(
                        health.checks.backup.details.size_bytes /
                        1024
                      ).toFixed(1)} KB`
                    : "-"}
                </strong>
              </div>

              <div>
                <span>Saklama süresi</span>
                <strong>
                  {health.checks?.backup?.details?.retention_days
                    ? `${health.checks.backup.details.retention_days} gün`
                    : "-"}
                </strong>
              </div>

              <div>
                <span>Yedekleme aralığı</span>
                <strong>
                  {health.checks?.backup?.details?.interval_hours
                    ? `${health.checks.backup.details.interval_hours} saat`
                    : "-"}
                </strong>
              </div>

              <div>
                <span>Yedek yaşı</span>
                <strong>
                  {health.checks?.backup?.details?.age_hours !== null &&
                  health.checks?.backup?.details?.age_hours !== undefined
                    ? `${health.checks.backup.details.age_hours.toFixed(1)} saat`
                    : "-"}
                </strong>
              </div>

              <div>
                <span>Veritabanı</span>
                <strong>
                  {health.checks?.backup?.details?.database || "-"}
                </strong>
              </div>
            </div>
          </section>

          <section className="platform-health-containers">
            <div className="platform-health-section-title">
              <div>
                <p>Runtime</p>
                <h2>Container Durumu</h2>
              </div>

              <span>
                Toplam {health.checks?.containers?.summary?.total || 0} servis
              </span>
            </div>

            <div className="platform-health-container-list">
              {(health.checks?.containers?.items || []).map((container) => {
                const expectedStopped =
                  container.name.includes("migrate") &&
                  container.state === "exited";

                const healthyContainer =
                  container.state === "running" &&
                  container.health !== "unhealthy";

                const displayHealthy = healthyContainer || expectedStopped;

                return (
                  <article
                    key={container.id}
                    className={`platform-health-container-row ${
                      displayHealthy ? "healthy" : "unhealthy"
                    }`}
                  >
                    <div>
                      <strong>{container.name}</strong>
                      <span>{container.image}</span>
                    </div>

                    <div className="platform-health-container-state">
                      <strong>
                        {expectedStopped
                          ? "Tamamlandı"
                          : container.state === "running"
                            ? "Çalışıyor"
                            : "Durmuş"}
                      </strong>
                      <span>{container.status}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="platform-health-meta">
            <div>
              <span>Tenant</span>
              <strong>{health.tenant_id}</strong>
            </div>
            <div>
              <span>Kontrol eden kullanıcı</span>
              <strong>{health.actor}</strong>
            </div>
            <div>
              <span>Request ID</span>
              <strong>{health.request_id}</strong>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
