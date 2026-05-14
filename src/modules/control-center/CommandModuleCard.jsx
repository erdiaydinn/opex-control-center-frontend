import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowUpRight,
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

export default function CommandModuleCard({ module, index }) {
  const Icon = iconMap[module.icon] || Sparkles;
  const isActive = module.status === "active";

  const card = (
    <motion.article
      className={`cc-module-card ${isActive ? "is-active" : "is-locked"}`}
      initial={{ opacity: 0, y: 26, rotateX: 5 }}
      animate={{ opacity: 1, y: 0, rotateX: 0 }}
      transition={{ duration: 0.55, delay: 0.1 + index * 0.06, ease: "easeOut" }}
      whileHover={
        isActive
          ? {
              y: -8,
              rotateX: 2,
              rotateY: -2,
              scale: 1.015,
            }
          : {}
      }
    >
      <div className="cc-module-shine" />

      <div className="cc-module-card-header">
        <div className="cc-module-icon">
          <Icon size={22} />
        </div>

        <span className={`cc-status ${isActive ? "active" : "soon"}`}>
          {isActive ? (
            module.statusLabel
          ) : (
            <>
              <Lock size={13} /> {module.statusLabel}
            </>
          )}
        </span>
      </div>

      <div className="cc-module-body">
        <p className="cc-module-kicker">0{index + 1} / {module.signal}</p>
        <h3>{module.title}</h3>
        <p>{module.subtitle}</p>
      </div>

      <div className="cc-module-footer">
        <span>{module.metric}</span>
        <ArrowUpRight size={18} />
      </div>
    </motion.article>
  );

  if (!isActive) {
    return <div className="cc-module-disabled">{card}</div>;
  }

  return (
    <Link to={module.route} className="cc-module-link">
      {card}
    </Link>
  );
}
