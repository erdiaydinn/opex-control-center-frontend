import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import GlobalTextTranslator from "./i18n/GlobalTextTranslator.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
    <GlobalTextTranslator />
  </React.StrictMode>
);
