
import React, { useEffect, useState } from "react";
import "./PremiumLoading.css";

export default function PremiumLoading({
  title = "Building live warehouse mesh",
  subtitle = "Depot grid, zone lights, SKU nodes and AI route graph are coming online.",
}) {
  const [progress, setProgress] = useState(0);
  const phases = [
    "Booting EA Intelligence Core",
    "Building depot mesh",
    "Connecting SKU nodes",
    "Opening zone lights",
    "Optimizing route graph",
    "Rendering command center",
  ];

  useEffect(() => {
    const t = setInterval(() => {
      setProgress((p) => Math.min(100, p + 1));
    }, 34);
    return () => clearInterval(t);
  }, []);

  const phaseIndex = Math.min(phases.length - 1, Math.floor(progress / (100 / phases.length)));

  return (
    <div className="pl-final-overlay">
      <div className="pl-final-grain" />
      <div className="pl-final-orb pink" />
      <div className="pl-final-orb cyan" />

      <div className="pl-final-card">
        <section className="pl-final-scene">
          <div className="pl-final-floor">
            <div className="pl-final-edge" />

            {Array.from({ length: 7 }).map((_, i) => (
              <div
                key={i}
                className="pl-final-rack"
                style={{
                  "--x": `${15 + (i % 4) * 17}%`,
                  "--y": `${18 + Math.floor(i / 4) * 32}%`,
                  "--delay": `${i * 0.12}s`,
                }}
              >
                {Array.from({ length: 18 }).map((_, p) => <i key={p} />)}
              </div>
            ))}

            <div className="pl-final-zone chilled">+4</div>
            <div className="pl-final-zone frozen">-18</div>
            <div className="pl-final-zone refill">REFILL</div>

            <svg className="pl-final-route" viewBox="0 0 100 100" preserveAspectRatio="none">
              <path d="M8,76 C20,62 30,52 42,54 C55,56 54,32 67,35 C80,38 76,64 91,70" />
            </svg>

            <div className="pl-final-node n1" />
            <div className="pl-final-node n2" />
            <div className="pl-final-node n3" />
            <div className="pl-final-transpallet" />
          </div>
        </section>

        <section className="pl-final-copy">
          <div className="pl-final-core">
            <span>EA INTELLIGENCE CORE</span>
            <b>ONLINE</b>
          </div>

          <div>
            <h3>{title}</h3>
            <p>{subtitle}</p>

            <div className="pl-final-phase">
              <span>{phases[phaseIndex]}</span>
              <b>{progress}%</b>
            </div>

            <div className="pl-final-bar">
              <i style={{ width: `${progress}%` }} />
            </div>

            <div className="pl-final-steps">
              {phases.map((p, i) => (
                <em key={p} className={i <= phaseIndex ? "active" : ""}>
                  {p}
                </em>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
