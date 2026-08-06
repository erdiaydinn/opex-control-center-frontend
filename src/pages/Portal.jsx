import React from "react";
import { Boxes, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function Portal() {
  const navigate = useNavigate();

  const modules = [
    {
      key: "planogram",
      name: "Planogram Studio",
      description: "Planogram, raf, fixture ve 3D mağaza yerleşim optimizasyonu.",
      path: "/planogram",
      status: "ACTIVE",
    },
    {
      key: "budget",
      name: "Bütçe Takibi",
      description: "OPEX / CAPEX, PO, fatura, kategori ve dönemsel bütçe zekâsı.",
      path: "/budget",
      status: "ACTIVE",
    },
    {
      key: "dockos",
      name: "DockOS",
      description: "Inbound Intelligence & Dock Scheduling Platform.",
      path: "/dockos",
      status: "ACTIVE",
    },
  ];

  return (
    <main className="portal-shell">
      <header className="portal-header">
        <div>
          <p className="eyebrow">Ana Portal</p>
          <h1>EAY OneOps</h1>
        </div>
      </header>

      <section className="hero-panel">
        <div>
          <p className="eyebrow">Operasyon platformu</p>
          <h2>Modüller</h2>
          <p>Operasyon ekranları aşağıda listelenir.</p>
        </div>
        <Sparkles size={38} />
      </section>

      <section className="module-grid">
        {modules.map((module) => (
          <button
            key={module.key}
            className="module-card"
            onClick={() => navigate(module.path)}
          >
            <div className="module-icon">
              <Boxes size={22} />
            </div>
            <div>
              <p className="module-status">{module.status}</p>
              <h3>{module.name}</h3>
              <p>{module.description}</p>
            </div>
          </button>
        ))}
      </section>
    </main>
  );
}
