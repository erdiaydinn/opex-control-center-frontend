import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthContext.jsx";

const PLANAI_URL =
  import.meta.env.VITE_PLANAI_LEGACY_URL || "http://localhost:5174";

const PLANOGRAM_FEATURES = [
  "layoutView",
  "layoutEdit",
  "fixtureEdit",
  "ruleEdit",
  "productAssign",
  "aiRecommend",
];

const PLANOGRAM_ACTIONS = [
  "view",
  "create",
  "edit",
  "approve",
  "export",
  "delete",
];

function getOpexAccessToken() {
  if (typeof window === "undefined") return "";
  const keys = ["opex_access_token", "opex_session_token"];
  for (const key of keys) {
    const value = window.sessionStorage.getItem(key) || window.localStorage.getItem(key);
    if (value) return value;
  }
  return "";
}

export default function PlanogramStudio() {
  const frameRef = useRef(null);
  const [bridgeState, setBridgeState] = useState("connecting");
  const {
    user,
    can,
    canFeature,
    canAction,
    getModuleScope,
    isSuperAdmin,
  } = useAuth();

  const targetOrigin = useMemo(() => new URL(PLANAI_URL, window.location.href).origin, []);

  const payload = useMemo(() => {
    const superAdmin =
      typeof isSuperAdmin === "function" ? isSuperAdmin() : Boolean(isSuperAdmin);

    return {
      user: {
        email: user?.email,
        name: user?.name || user?.email,
        role: user?.role,
      },
      permissions: {
        module: "planogram",
        view: superAdmin || can("planogram", "view"),
        admin: superAdmin || can("planogram", "admin"),
        features: Object.fromEntries(
          PLANOGRAM_FEATURES.map((key) => [
            key,
            superAdmin || canFeature("planogram", key),
          ])
        ),
        actions: Object.fromEntries(
          PLANOGRAM_ACTIONS.map((key) => [
            key,
            superAdmin || canAction("planogram", key),
          ])
        ),
      },
      scope: getModuleScope("planogram"),
      accessToken: getOpexAccessToken(),
      locale: document.documentElement.lang || "tr",
      theme: window.localStorage.getItem("opex_theme") || "light",
      issuedAt: new Date().toISOString(),
    };
  }, [can, canAction, canFeature, getModuleScope, isSuperAdmin, user]);

  const sendSession = useCallback(() => {
    if (!frameRef.current?.contentWindow) return;
    frameRef.current.contentWindow.postMessage(
      { type: "OPEX_PLANOGRAM_SESSION", version: 1, payload },
      targetOrigin
    );
  }, [payload, targetOrigin]);

  useEffect(() => {
    if (bridgeState === "ready") return undefined;
    sendSession();
    const retry = window.setInterval(sendSession, 700);
    const deadline = window.setTimeout(() => setBridgeState("error"), 8000);
    return () => {
      window.clearInterval(retry);
      window.clearTimeout(deadline);
    };
  }, [bridgeState, sendSession]);

  useEffect(() => {
    function handleMessage(event) {
      if (event.origin !== targetOrigin || event.source !== frameRef.current?.contentWindow) {
        return;
      }
      if (event.data?.type === "PLANOGRAM_READY" && event.data?.version === 1) {
        sendSession();
      }
      if (event.data?.type === "PLANOGRAM_SESSION_ACCEPTED" && event.data?.version === 1) {
        setBridgeState("ready");
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [sendSession, targetOrigin]);

  return (
    <main style={{ width: "100vw", height: "100vh", background: "#f6f7fa", position: "relative" }}>
      {bridgeState !== "ready" ? (
        <div
          role="status"
          style={{
            position: "absolute",
            top: 16,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 2,
            display: "flex",
            alignItems: "center",
            gap: 10,
            color: bridgeState === "error" ? "#9f1239" : "#111827",
            background: "#fff",
            border: `1px solid ${bridgeState === "error" ? "#fecdd3" : "#e5e7eb"}`,
            borderRadius: 12,
            padding: "10px 14px",
            boxShadow: "0 12px 32px rgba(15,23,42,.12)",
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          <span>{bridgeState === "error" ? "Planogram oturumu 8 saniyede doğrulanamadı." : "Planogram oturumu doğrulanıyor…"}</span>
          {bridgeState === "error" ? (
            <button
              type="button"
              onClick={() => { setBridgeState("connecting"); sendSession(); }}
              style={{ border: 0, borderRadius: 8, background: "#df1067", color: "#fff", padding: "7px 10px", fontWeight: 800 }}
            >
              Yeniden dene
            </button>
          ) : null}
        </div>
      ) : null}

      <iframe
        ref={frameRef}
        title="Planogram Studio"
        src={PLANAI_URL}
        onLoad={sendSession}
        allow="clipboard-read; clipboard-write"
        style={{
          width: "100%",
          height: "100%",
          border: "0",
          display: "block",
          background: "#f6f7fa",
        }}
      />
    </main>
  );
}
