import React, { useCallback, useEffect, useState } from "react";
import { Award, BadgeCheck, Clock3, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";

import { apiGet } from "../../api/client.js";
import { translateAcademyExpansion } from "../../platform/i18n/academyExpansionMessages.js";
import "./academy-expansion.css";

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return String(value[locale] || value.en || value.tr || Object.values(value).find(Boolean) || "");
}

function credentialState(item) {
  if (item.revoked) return "revoked";
  if (item.expired) return "expired";
  return "valid";
}

export default function AcademyAchievements({ locale, t, formatDate }) {
  const tx = (key) => translateAcademyExpansion(locale, key);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await apiGet("/v1/academy/credentials/me");
      setItems(payload?.items || []);
    } catch (reason) {
      setItems([]);
      setError(reason instanceof Error && reason.message ? reason.message : t("academyLoadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="eay-academy-expansion-card" aria-busy={loading ? "true" : "false"}>
      <header className="eay-academy-expansion-head">
        <div>
          <span><ShieldCheck size={16} aria-hidden="true" /> EAY Academy</span>
          <h2>{tx("achievements")}</h2>
          <p>{tx("achievementsHint")}</p>
        </div>
        <button type="button" className="eay-academy-secondary" onClick={load} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={15} aria-hidden="true" />
          {tx("refresh")}
        </button>
      </header>

      {loading ? <p role="status"><LoaderCircle className="spin" size={18} aria-hidden="true" /> {t("loading")}</p> : null}
      {!loading && error ? <p className="eay-academy-inline-error" role="alert">{error}</p> : null}
      {!loading && !error && !items.length ? <div data-eay-product-state="empty" role="status"><Award size={24} aria-hidden="true" /><p>{tx("noCredentials")}</p></div> : null}
      {!loading && !error && items.length ? (
        <div className="eay-academy-achievement-grid" data-eay-product-state="ready">
          {items.map((item) => {
            const state = credentialState(item);
            const stateLabel = state === "revoked" ? tx("revokedCredential") : state === "expired" ? tx("expiredCredential") : tx("validCredential");
            return (
              <article className="eay-academy-achievement-card" key={item.badge_award_id}>
                <header>
                  <div><BadgeCheck size={26} aria-hidden="true" /></div>
                  <span className={`eay-academy-credential-state is-${state}`}><span aria-hidden="true">●</span>{stateLabel}</span>
                </header>
                <div>
                  <h3>{localized(item.title_i18n, locale) || item.badge_key}</h3>
                  <p>{localized(item.description_i18n, locale)}</p>
                </div>
                <dl>
                  <dt>{tx("observedLevel")}</dt><dd>{item.observed_level}/5</dd>
                  <dt>{tx("evidence")}</dt><dd>{item.evidence_type} · {item.evidence_ref}</dd>
                  <dt>{tx("issuedAt")}</dt><dd>{item.issued_at ? formatDate(item.issued_at, { dateStyle: "medium" }) : "—"}</dd>
                  <dt>{tx("expiresAt")}</dt><dd>{item.expires_at ? formatDate(item.expires_at, { dateStyle: "medium" }) : "—"}</dd>
                </dl>
                {!item.signed_portable_credential ? <small><Clock3 size={13} aria-hidden="true" /> {tx("portablePending")}</small> : null}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
