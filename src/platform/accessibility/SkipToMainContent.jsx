import React from "react";

import { usePlatformPreferences } from "../preferences/PlatformPreferencesContext.jsx";
import "./skip-to-main-content.css";

export default function SkipToMainContent() {
  const { t } = usePlatformPreferences();

  return (
    <a className="eay-skip-link" href="#eay-main-content">
      {t("skipToContent")}
    </a>
  );
}
