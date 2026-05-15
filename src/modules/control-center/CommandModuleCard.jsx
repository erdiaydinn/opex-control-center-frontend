import React from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  BarChart3,
  BookOpen,
  Boxes,
  Brain,
  ChevronRight,
  ClipboardCheck,
  LayoutGrid,
  Lock,
  ShieldCheck,
  Truck,
  UsersRound,
  WalletCards,
} from "lucide-react";
import clsx from "clsx";

const iconMap = {
  layout: LayoutGrid,
  dock: Truck,
  route: Truck,
  budget: WalletCards,
  academy: BookOpen,
  ai: Brain,
  cycle: ClipboardCheck,
  access: UsersRound,
  default: Boxes,
};

export default function CommandModuleCard({ module, index = 0 }) {
  const navigate = useNavigate();
  const Icon = iconMap[module.icon] || iconMap.default;
  const isDisabled = !module.enabled || !module.route || module.route === "#";

  function openModule() {
    if (isDisabled) return;

    if (module.lastUsedKey) {
      window.localStorage.setItem(module.lastUsedKey, new Date().toISOString());
    }

    navigate(module.route);
  }

  return (
    <motion.article
      className={clsx(
        "ocx-module-card",
        `tone-${module.tone || "primary"}`,
        isDisabled && "is-disabled"
      )}
      initial={{ opacity: 0, y: 28, scale: 0.97, filter: "blur(10px)" }}
      animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
      transition={{
        duration: 0.58,
        delay: 0.08 + index * 0.055,
        ease: [0.16, 0.86, 0.22, 1],
      }}
      whileHover={
        isDisabled
          ? {}
          : {
              y: -8,
              scale: 1.015,
              transition: { duration: 0.18 },
            }
      }
      onClick={openModule}
      role="button"
      tabIndex={isDisabled ? -1 : 0}
      onKeyDown={(e) => {
        if (!isDisabled && (e.key === "Enter" || e.key === " ")) openModule();
      }}
    >
      <div className="ocx-card-glare" />

      <div className="ocx-card-top">
        <div className="ocx-module-icon">
          <Icon size={24} />
        </div>

        <div className={clsx("ocx-health", module.health)}>
          {module.health === "healthy" ? <ShieldCheck size={14} /> : <Lock size={14} />}
          {module.healthLabel}
        </div>
      </div>

      <div className="ocx-card-body">
        <span>{module.group}</span>
        <h3>{module.title}</h3>
        <p>{module.description}</p>
      </div>

      <div className="ocx-card-meta">
        <div>
          <small>Scope</small>
          <strong>{module.meta}</strong>
        </div>

        <div className="ocx-shortcut">
          <small>Shortcut</small>
          <strong>{module.shortcut}</strong>
        </div>
      </div>

      <div className="ocx-card-action">
        <span>{isDisabled ? "Hazırlanıyor" : "Modüle gir"}</span>
        {isDisabled ? <Lock size={17} /> : <ChevronRight size={18} />}
      </div>

      <BarChart3 className="ocx-card-watermark" size={120} />
    </motion.article>
  );
}
