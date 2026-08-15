import React, { useEffect, useState } from "react";

import { usePlatformPreferences } from "../preferences/PlatformPreferencesContext.jsx";
import "./network-status-announcer.css";

function readOnlineState() {
  return typeof navigator === "undefined" ? true : navigator.onLine !== false;
}

export default function NetworkStatusAnnouncer() {
  const { t } = usePlatformPreferences();
  const [online, setOnline] = useState(readOnlineState);

  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  if (online) return null;

  return (
    <div
      className="eay-network-status"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-eay-network-state="offline"
    >
      {t("offline")}
    </div>
  );
}
