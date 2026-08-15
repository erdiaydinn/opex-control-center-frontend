import React from "react";

import { usePlatformPreferences } from "../preferences/PlatformPreferencesContext.jsx";

class RouteErrorBoundaryCore extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
    this.headingRef = React.createRef();
    this.retry = this.retry.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep the browser console useful for repository/staging diagnosis without
    // rendering raw exception details or stack traces into the product surface.
    console.error("EAY route render failure", error, info);
  }

  componentDidMount() {
    if (this.state.error) {
      this.headingRef.current?.focus();
    }
  }

  componentDidUpdate(previousProps, previousState) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
      return;
    }
    if (!previousState.error && this.state.error) {
      this.headingRef.current?.focus();
    }
  }

  retry() {
    // React.lazy caches a rejected import promise. Merely clearing this boundary can
    // therefore render the same failed lazy route forever after a transient chunk or
    // deployment-cache failure. A user-requested retry performs a clean document
    // reload so the browser can resolve the current chunk graph. Keep a non-browser
    // fallback for test/SSR environments.
    if (typeof window !== "undefined" && typeof window.location?.reload === "function") {
      window.location.reload();
      return;
    }
    this.setState({ error: null });
  }

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    const { t } = this.props;
    return (
      <section
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        data-eay-product-state="error"
        style={{ maxWidth: 720, margin: "48px auto", padding: 24 }}
      >
        <h1 tabIndex="-1" ref={this.headingRef}>
          {t("errorTitle")}
        </h1>
        <p>{t("retry")}</p>
        <button type="button" onClick={this.retry}>
          {t("retry")}
        </button>
      </section>
    );
  }
}

export default function RouteErrorBoundary({ children, resetKey }) {
  const { t } = usePlatformPreferences();
  return (
    <RouteErrorBoundaryCore t={t} resetKey={resetKey}>
      {children}
    </RouteErrorBoundaryCore>
  );
}
