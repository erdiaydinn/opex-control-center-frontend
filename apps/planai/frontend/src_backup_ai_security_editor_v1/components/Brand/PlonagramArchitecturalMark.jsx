import React from "react";

export default function PlonagramArchitecturalMark({ className = "pl-architect-mark" }) {
  return (
    <svg className={className} viewBox="0 0 180 180" role="img" aria-label="Plonagram">
      <path className="pl-line" d="M55 129V54l34-20 44 25v48l-39 23-39-22" />
      <path className="pl-line" d="M55 54l39 22 39-17" />
      <path className="pl-line" d="M94 76v54" />
      <path className="pl-line" d="M55 129l39-23 39 1" />
      <path className="pl-line" d="M94 106l22-13 17 14" />
      <path className="pl-line" d="M94 76l22-13 17-4" />
      <path className="pl-line pl-accent" d="M116 93l26-15v29l-26 15" />
    </svg>
  );
}
