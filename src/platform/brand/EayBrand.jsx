import React from "react";

const BRAND_LABELS = Object.freeze({
  master: "EAY",
  one: "EAY One",
  terminal: "EAY Terminal",
});

function MasterGlyph() {
  return (
    <>
      <path className="eay-fill-navy" d="M7 12h50L46 28H7V12Zm0 28h39L35 56H7V40Zm0 28h43l34-56h20L70 80H7V68Z" />
      <path className="eay-fill-navy" d="M76 55 102 12h19L95 55l24 25H97L76 55Z" />
      <path className="eay-fill-navy" d="m107 12 13 17 13-17h18l-31 40-21-27 8-13Z" />
      <path className="eay-fill-magenta" d="m70 77 11-18 9 12-5 9H68l2-3Z" />
    </>
  );
}

function MasterMark() {
  return (
    <svg className="eay-brand-svg" viewBox="0 0 158 92" aria-hidden="true" focusable="false">
      <MasterGlyph />
    </svg>
  );
}

function OneMark() {
  return (
    <svg className="eay-brand-svg" viewBox="0 0 282 104" aria-hidden="true" focusable="false">
      <path className="eay-stroke-navy" d="M24 58A43 43 0 0 1 95 25" />
      <circle className="eay-fill-white eay-stroke-navy-thin" cx="101" cy="22" r="6" />
      <path className="eay-stroke-magenta" d="M33 75a43 43 0 0 0 30 18" />
      <circle className="eay-fill-white eay-stroke-navy-thin" cx="70" cy="94" r="6" />
      <path className="eay-stroke-navy" d="M78 94a43 43 0 0 0 35-23" />
      <g transform="translate(24 28) scale(.58)"><MasterGlyph /></g>
      <text className="eay-wordmark eay-fill-navy" x="128" y="73">One</text>
    </svg>
  );
}

function TerminalMark() {
  return (
    <svg className="eay-brand-svg" viewBox="0 0 304 104" aria-hidden="true" focusable="false">
      <g transform="translate(7 12)">
        <path className="eay-stroke-navy-terminal" d="M22 34V12h22M68 12h22v22M22 58v22h22M90 58v22H68" />
        <path className="eay-stroke-blue-terminal" d="M48 34v24m10-24v24m10-24v24" />
        <path className="eay-stroke-navy-thin" d="M51 12v10M51 70v10M12 46h10M90 46h10" />
      </g>
      <g transform="translate(113 14) scale(.72)"><MasterGlyph /></g>
      <text className="eay-terminal-word eay-fill-blue" x="139" y="96">TERMINAL</text>
    </svg>
  );
}

export default function EayBrand({
  variant = "master",
  compact = false,
  className = "",
  label,
}) {
  const resolved = variant === "one" || variant === "terminal" ? variant : "master";
  const accessibleLabel = label || BRAND_LABELS[resolved];
  const classes = ["eay-brand", `eay-brand--${resolved}`, compact ? "is-compact" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={classes} role="img" aria-label={accessibleLabel}>
      {resolved === "one" ? <OneMark /> : resolved === "terminal" ? <TerminalMark /> : <MasterMark />}
    </span>
  );
}
