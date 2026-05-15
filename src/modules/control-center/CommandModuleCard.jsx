import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  BrainCircuit,
  GraduationCap,
  LayoutDashboard,
  Lock,
  PackageCheck,
  Route as RouteIcon,
  Sparkles,
} from "lucide-react";

const iconMap = {
  layout: LayoutDashboard,
  route: RouteIcon,
  budget: BarChart3,
  academy: GraduationCap,
  ai: BrainCircuit,
  cycle: PackageCheck,
};

function formatLastUsed(key) {
  if (typeof window === "undefined") return "Henüz açılmadı";

  const raw = window.localStorage.getItem(key);
  if (!raw) return "Henüz açılmadı";

  const last = Number(raw);
  if (!last) return "Henüz açılmadı";

  const diffMs = Date.now() - last;
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return "Az önce açıldı";
  if (diffMin < 60) return `${diffMin} dk önce`;
  if (diffMin < 1440) return `${Math.floor(diffMin / 60)} saat önce`;

  return `${Math.floor(diffMin / 1440)} gün önce`;
}

export default function CommandModuleCard({ module, index }) {
  const Icon = iconMap[module.icon] || Sparkles;

  const lastUsed = useMemo(() => {
    return formatLastUsed(module.lastUsedKey);
  }, [module.lastUsedKey]);

  const handleOpen = () => {
    if (!module.enabled) return;
    window.localStorage.setItem(module.lastUsedKey, String(Date.now()));
  };

  const card = (
    <motion.article
      className={`opgrid-card health-${module.health} ${module.enabled ? "is-enabled" : "is-disabled"}`}
      initial={{ opacity: 0, y: 26 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        stiffness: 260,
        damping: 24,
        delay: 0.08 + index * 0.045,
      }}
      whileHover={
        module.enabled
          ? {
              scale: 1.018,
              y: -4,
            }
          : {}
      }
      whileTap={
        module.enabled
          ? {
              scale: 0.982,
              y: 3,
            }
          : {}
      }
    >
      <div className="opgrid-status-bar" />

      <div className="opgrid-card-head">
        <div className="opgrid-icon-wrap">
          <Icon size={26} />
        </div>

        <div className="opgrid-shortcut">{module.shortcut}</div>
      </div>

      <div className="opgrid-card-body">
        <span className="opgrid-group">{module.group}</span>
        <h2>{module.title}</h2>
        <p>{module.description}</p>
      </div>

      <div className="opgrid-card-foot">
        <div>
          <span className={`opgrid-health-dot ${module.health}`} />
          <strong>{module.healthLabel}</strong>
        </div>

        <div className="opgrid-last-used">
          {module.enabled ? lastUsed : "Hazırlık aşamasında"}
        </div>
      </div>

      <div className="opgrid-open-row">
        <span>{module.enabled ? "Modülü aç" : "Yakında aktif olacak"}</span>
        {module.enabled ? <ArrowRight size={18} /> : <Lock size={16} />}
      </div>
    </motion.article>
  );

  if (!module.enabled) {
    return <div className="opgrid-card-link disabled">{card}</div>;
  }

  return (
    <Link to={module.route} className="opgrid-card-link" onClick={handleOpen}>
      {card}
    </Link>
  );
}
