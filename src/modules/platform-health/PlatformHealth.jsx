import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowLeft,
  Database,
  RefreshCw,
  Server,
  ShieldCheck,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiFetchWithStatus } from "../../api/client.js";
import { translatePlatformHealth } from "../../platform/i18n/platformHealthMessages.js";
import { translateSecurityGuardian } from "../../platform/i18n/securityGuardianMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./platform-health.css";
import "./platform-health-quality.css";
import "./platform-health-guardian.css";

const HEALTHY_STATES = new Set(["ok", "healthy", "success"]);

function statusMessageKey(status) {
  if (HEALTHY_STATES.has(status)) return "operational";
  if (status === "warning") return "warning";
  if (status === "stale") return "stale";
  if (status === "failed" || status === "unhealthy") return "failed";
  if (status === "unavailable") return "unavailable";
  return "attentionRequired";
}

function isHealthDiagnosticResult(result) {
  if (!result) return false;
  if (result.ok && result.data?.checks) return true;
  return (
    result.status === 503 &&
    result.data?.status === "degraded" &&
    Boolean(result.data?.checks)
  );
}

function StatusCard({ title, status, detail, icon: Icon, ph, successLabel }) {
  const healthy = HEALTHY_STATES.has(status);
  const statusLabel = healthy
    ? successLabel || ph("operational")
    : ph(statusMessageKey(status));

  return (
    <article
      className={`platform-health-card ${healthy ? "healthy" : "unhealthy"}`}
      data-service-status={status || "unknown"}
    >
      <div className="platform-health-card-icon" aria-hidden="true">
        <Icon size={22} />
      </div>

      <div>
        <span>{title}</span>
        <strong>{statusLabel}</strong>
        {detail ? <small>{detail}</small> : null}
      </div>
    </article>
  );
}

function GuardianPanel({ guardian, state, sg, formatNumber }) {
  if (state === "loading") {
    return (
      <section
        className="platform-health-guardian is-loading"
        role="status"
        aria-live="polite"
        aria-busy="true"
        data-guardian-state="loading"
      >
        <ShieldCheck size={22} aria-hidden="true" />
        <strong>{sg("loading")}</strong>
      </section>
    );
  }

  if (state !== "ready" || !guardian) {
    return (
      <section
        className="platform-health-guardian is-unavailable"
        role="status"
        aria-live="polite"
        data-guardian-state="unavailable"
      >
        <ShieldCheck size={22} aria-hidden="true" />
        <div>
          <strong>{sg("title")}</strong>
          <span>{sg("unavailable")}</span>
        </div>
      </section>
    );
  }

  const threatSources = Array.isArray(guardian.threat_intelligence)
    ? guardian.threat_intelligence
    : [];
  const blockers = Array.isArray(guardian.blockers) ? guardian.blockers : [];
  const observed = Boolean(guardian.last_observed_at);

  return (
    <section
      className="platform-health-guardian"
      aria-labelledby="platform-health-guardian-title"
      data-guardian-state="ready"
    >
      <header>
        <div className="platform-health-guardian-title">
          <ShieldCheck size={24} aria-hidden="true" />
          <div>
            <p>{sg("readOnlyAssessment")}</p>
            <h2 id="platform-health-guardian-title">{sg("title")}</h2>
            <span>{sg("subtitle")}</span>
          </div>
        </div>
        <strong>{guardian.production_ready ? sg("productionReady") : sg("noObservation")}</strong>
      </header>

      <div className="platform-health-guardian-grid">
        <article>
          <span>{sg("observationState")}</span>
          <strong>{observed ? guardian.last_observed_at : sg("unknownWithoutEvidence")}</strong>
        </article>
        <article>
          <span>{sg("humanApproval")}</span>
          <strong>{guardian.release_policy?.human_approval_required ? sg("required") : sg("disabled")}</strong>
        </article>
        <article>
          <span>{sg("automaticRemediation")}</span>
          <strong>{guardian.release_policy?.automatic_production_remediation ? sg("required") : sg("disabled")}</strong>
        </article>
        <article>
          <span>{sg("productionReady")}</span>
          <strong>{guardian.production_ready ? sg("required") : sg("no")}</strong>
        </article>
      </div>

      <div className="platform-health-guardian-detail-grid">
        <div>
          <div className="platform-health-guardian-subhead">
            <strong>{sg("threatSources")}</strong>
            <span>{formatNumber(threatSources.length)}</span>
          </div>
          <ul>
            {threatSources.map((source) => (
              <li key={source.source_id}>
                <code>{source.source_id}</code>
                <span>{source.integration_state === "not_connected" ? sg("notConnected") : source.integration_state}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <div className="platform-health-guardian-subhead">
            <strong>{sg("blockers")}</strong>
            <span>{formatNumber(blockers.length)}</span>
          </div>
          <ul>
            {blockers.map((blocker) => (
              <li key={blocker}><code>{blocker}</code></li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

export default function PlatformHealth() {
  const navigate = useNavigate();
  const { locale, formatDate, formatNumber, t } = usePlatformPreferences();
  const ph = useCallback(
    (key, params) => translatePlatformHealth(locale, key, params),
    [locale]
  );
  const sg = useCallback(
    (key) => translateSecurityGuardian(locale, key),
    [locale]
  );

  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [guardian, setGuardian] = useState(null);
  const [guardianState, setGuardianState] = useState("loading");

  const loadHealth = useCallback(async () => {
    setLoading(true);
    setError(false);
    setGuardianState("loading");

    const [healthResult, guardianResult] = await Promise.all([
      apiFetchWithStatus("/v1/platform/health", { method: "GET" }).catch(() => null),
      apiFetchWithStatus("/v1/platform/security-guardian/workspace", { method: "GET" }).catch(() => null),
    ]);

    if (isHealthDiagnosticResult(healthResult)) {
      setHealth(healthResult.data);
      setError(false);
    } else {
      setHealth(null);
      setError(true);
    }

    if (
      guardianResult?.ok &&
      guardianResult.data?.scope === "eay_platform" &&
      guardianResult.data?.visibility === "platform_admin_only"
    ) {
      setGuardian(guardianResult.data);
      setGuardianState("ready");
    } else {
      setGuardian(null);
      setGuardianState("unavailable");
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    loadHealth();
  }, [loadHealth]);

  const productState = loading ? "loading" : error ? "error" : health ? "ready" : "empty";

  const backupCompletedAt = health?.checks?.backup?.details?.completed_at || null;
  const backupDate = useMemo(() => {
    if (!backupCompletedAt) return null;
    try {
      return formatDate(backupCompletedAt, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch {
      return null;
    }
  }, [backupCompletedAt, formatDate]);

  const sizeLabel = useMemo(() => {
    const raw = Number(health?.checks?.backup?.details?.size_bytes);
    if (!Number.isFinite(raw) || raw < 0) return "—";
    if (raw >= 1024 * 1024) {
      return ph("megabytesValue", { value: formatNumber(raw / (1024 * 1024)) });
    }
    if (raw >= 1024) {
      return ph("kilobytesValue", { value: formatNumber(raw / 1024) });
    }
    return ph("bytesValue", { value: formatNumber(raw) });
  }, [formatNumber, health, ph]);

  const retentionLabel = health?.checks?.backup?.details?.retention_days
    ? ph("daysValue", {
        value: formatNumber(health.checks.backup.details.retention_days),
      })
    : "—";
  const intervalLabel = health?.checks?.backup?.details?.interval_hours
    ? ph("hoursValue", {
        value: formatNumber(health.checks.backup.details.interval_hours),
      })
    : "—";
  const ageHours = health?.checks?.backup?.details?.age_hours;
  const ageLabel = ageHours !== null && ageHours !== undefined
    ? ph("hoursValue", { value: formatNumber(ageHours) })
    : "—";

  return (
    <main
      className="platform-health-page"
      data-eay-product-state={productState}
      aria-busy={loading}
    >
      <header className="platform-health-header">
        <div>
          <button
            type="button"
            className="platform-health-back"
            onClick={() => navigate("/")}
          >
            <ArrowLeft className="platform-health-back-icon" size={18} aria-hidden="true" />
            {t("back")}
          </button>

          <p>{ph("platformCore")}</p>
          <h1>{ph("title")}</h1>
          <span>{ph("subtitle")}</span>
        </div>

        <button
          type="button"
          className="platform-health-refresh"
          onClick={loadHealth}
          disabled={loading}
          aria-busy={loading}
        >
          <RefreshCw size={18} className={loading ? "spinning" : ""} aria-hidden="true" />
          {loading ? ph("checking") : t("refresh")}
        </button>
      </header>

      {loading ? (
        <section
          className="platform-health-loading"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <Activity size={20} aria-hidden="true" />
          <strong>{ph("checking")}</strong>
        </section>
      ) : null}

      {error ? (
        <section className="platform-health-error" role="alert" aria-live="assertive">
          <strong>{ph("loadError")}</strong>
          <button type="button" onClick={loadHealth}>
            {t("retry")}
          </button>
        </section>
      ) : null}

      {health ? (
        <>
          <section
            className={`platform-health-summary ${health.status}`}
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <Activity size={24} aria-hidden="true" />
            <div>
              <strong>
                {health.status === "healthy"
                  ? ph("healthySummary")
                  : ph("degradedSummary")}
              </strong>
              <span>
                {ph("environmentVersion", {
                  environment: health.environment || "—",
                  version: health.version || "—",
                })}
              </span>
            </div>
          </section>

          <section className="platform-health-grid">
            <StatusCard
              title={ph("coreApi")}
              status={health.checks?.api?.status}
              detail={ph("versionDetail", {
                version: health.checks?.api?.version || "—",
              })}
              icon={Server}
              ph={ph}
            />

            <StatusCard
              title={ph("postgresql")}
              status={health.checks?.database?.status}
              detail={ph("databaseDetail")}
              icon={Database}
              ph={ph}
            />

            <StatusCard
              title={ph("redis")}
              status={health.checks?.redis?.status}
              detail={ph("redisDetail")}
              icon={Activity}
              ph={ph}
            />

            <StatusCard
              title={ph("containerServices")}
              status={health.checks?.containers?.status}
              detail={ph("containerSummary", {
                running: formatNumber(health.checks?.containers?.summary?.running || 0),
                stopped: formatNumber(health.checks?.containers?.summary?.stopped || 0),
              })}
              icon={Server}
              ph={ph}
            />

            <StatusCard
              title={ph("databaseBackup")}
              status={health.checks?.backup?.status}
              successLabel={ph("successful")}
              detail={backupDate
                ? ph("lastBackupDetail", { date: backupDate })
                : ph("noBackupInfo")}
              icon={Database}
              ph={ph}
            />
          </section>

          <GuardianPanel
            guardian={guardian}
            state={guardianState}
            sg={sg}
            formatNumber={formatNumber}
          />

          <section className="platform-health-backup">
            <div className="platform-health-section-title">
              <div>
                <p>{ph("dataProtection")}</p>
                <h2>{ph("lastDatabaseBackup")}</h2>
              </div>

              <span>
                {HEALTHY_STATES.has(health.checks?.backup?.status)
                  ? ph("successful")
                  : ph(statusMessageKey(health.checks?.backup?.status))}
              </span>
            </div>

            <div className="platform-health-backup-grid">
              <div>
                <span>{ph("completionTime")}</span>
                <strong>{backupDate || "—"}</strong>
              </div>

              <div>
                <span>{ph("file")}</span>
                <strong>{health.checks?.backup?.details?.filename || "—"}</strong>
              </div>

              <div>
                <span>{ph("size")}</span>
                <strong>{sizeLabel}</strong>
              </div>

              <div>
                <span>{ph("retentionPeriod")}</span>
                <strong>{retentionLabel}</strong>
              </div>

              <div>
                <span>{ph("backupInterval")}</span>
                <strong>{intervalLabel}</strong>
              </div>

              <div>
                <span>{ph("backupAge")}</span>
                <strong>{ageLabel}</strong>
              </div>

              <div>
                <span>{ph("database")}</span>
                <strong>{health.checks?.backup?.details?.database || "—"}</strong>
              </div>
            </div>
          </section>

          <section className="platform-health-containers">
            <div className="platform-health-section-title">
              <div>
                <p>{ph("runtime")}</p>
                <h2>{ph("containerStatus")}</h2>
              </div>

              <span>
                {ph("totalServices", {
                  count: formatNumber(health.checks?.containers?.summary?.total || 0),
                })}
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
                          ? ph("completed")
                          : container.state === "running"
                            ? ph("running")
                            : ph("stopped")}
                      </strong>
                      <span>{container.status || ph("unavailable")}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="platform-health-meta">
            <div>
              <span>{ph("tenant")}</span>
              <strong>{health.tenant_id || "—"}</strong>
            </div>
            <div>
              <span>{ph("checkedBy")}</span>
              <strong>{health.actor || "—"}</strong>
            </div>
            <div>
              <span>{ph("requestId")}</span>
              <strong>{health.request_id || "—"}</strong>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
