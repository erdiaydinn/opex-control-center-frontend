import React, { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

const ROUTE_TARGET_SELECTOR = "main, [role='main'], #main-content";
const MODAL_SELECTOR = "[role='dialog'][aria-modal='true']";
const MAX_WAIT_MS = 3000;

const VISUALLY_HIDDEN_STYLE = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

function readableLabel(target) {
  const heading = target?.matches?.("h1") ? target : target?.querySelector?.("h1");
  const headingText = heading?.textContent?.trim();
  if (headingText) return headingText;
  return document.title?.trim() || "EAY";
}

function focusRouteTarget() {
  if (document.querySelector(MODAL_SELECTOR)) return false;

  const main = document.querySelector(ROUTE_TARGET_SELECTOR);
  const heading = main?.querySelector?.("h1") || document.querySelector("h1");
  const target = heading || main;
  if (!target) return false;

  if (!target.hasAttribute("tabindex")) {
    target.setAttribute("tabindex", "-1");
    target.dataset.eayRouteFocusTarget = "true";
  }
  target.focus({ preventScroll: true });
  return target;
}

export default function RouteAccessibility() {
  const location = useLocation();
  const previousPath = useRef(null);
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    const path = location.pathname;
    if (previousPath.current === null) {
      previousPath.current = path;
      return undefined;
    }
    if (previousPath.current === path) return undefined;
    previousPath.current = path;

    let cancelled = false;
    let observer;
    let timer;
    let firstFrame;
    let secondFrame;

    const settle = () => {
      if (cancelled) return false;
      const target = focusRouteTarget();
      if (!target) return false;
      setAnnouncement(readableLabel(target));
      observer?.disconnect();
      if (timer) window.clearTimeout(timer);
      return true;
    };

    firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        if (settle() || cancelled) return;
        const root = document.getElementById("root") || document.body;
        observer = new MutationObserver(() => settle());
        observer.observe(root, { childList: true, subtree: true });
        timer = window.setTimeout(() => {
          observer?.disconnect();
          if (!cancelled && !document.querySelector(MODAL_SELECTOR)) {
            const fallback = document.querySelector(ROUTE_TARGET_SELECTOR);
            if (fallback) setAnnouncement(readableLabel(fallback));
          }
        }, MAX_WAIT_MS);
      });
    });

    return () => {
      cancelled = true;
      if (firstFrame) window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
      observer?.disconnect();
      if (timer) window.clearTimeout(timer);
    };
  }, [location.pathname]);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-eay-route-announcer="true"
      style={VISUALLY_HIDDEN_STYLE}
    >
      {announcement}
    </div>
  );
}
