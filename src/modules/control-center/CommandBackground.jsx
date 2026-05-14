import React from "react";

export default function CommandBackground() {
  return (
    <div className="cc-bg" aria-hidden="true">
      <div className="cc-aurora cc-aurora-a" />
      <div className="cc-aurora cc-aurora-b" />
      <div className="cc-aurora cc-aurora-c" />

      <div className="cc-perspective-grid" />

      <div className="cc-orbit cc-orbit-one">
        <span />
        <span />
        <span />
      </div>

      <div className="cc-orbit cc-orbit-two">
        <span />
        <span />
      </div>

      <div className="cc-holo-deck">
        <div className="cc-holo-top">
          <i />
          <i />
          <i />
        </div>

        <div className="cc-holo-screen">
          <div className="cc-holo-sweep" />
          <div className="cc-holo-map">
            <span className="node n1" />
            <span className="node n2" />
            <span className="node n3" />
            <span className="node n4" />
            <span className="path p1" />
            <span className="path p2" />
            <span className="path p3" />
          </div>

          <div className="cc-holo-lines">
            <b />
            <b />
            <b />
          </div>
        </div>

        <div className="cc-holo-keyboard">
          {Array.from({ length: 28 }).map((_, index) => (
            <span key={index} className={index % 6 === 0 ? "is-hot" : ""} />
          ))}
        </div>
      </div>
    </div>
  );
}
