import React, { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  Eye,
  EyeOff,
  KeyRound,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext.jsx";
import { branding } from "../config/branding.js";

const DEMO_USERS = [
  {
    email: "erdi.aydin@yemeksepeti.com",
    label: "Super Admin",
    desc: "Tüm modüller ve yönetim erişimi",
  },
  {
    email: "admin@yemeksepeti.com",
    label: "Admin",
    desc: "Tüm modüller",
  },
  {
    email: "viewer@yemeksepeti.com",
    label: "Viewer",
    desc: "Planogram + DockOS",
  },
  {
    email: "noaccess@yemeksepeti.com",
    label: "No Access",
    desc: "Modül erişimi yok",
  },
];

/**
 * Görsel üzerindeki gerçek otomatik kapı alanı.
 * Yeni görsel için ayarlandı.
 *
 * Kapı biraz kayarsa sadece bu 4 değer oynanır:
 * left / top / width / height
 */
const DOOR_ON_IMAGE = {
  left: 0.424,
  top: 0.333,
  width: 0.165,
  height: 0.545,
};

function getCoverRect(containerWidth, containerHeight, imageWidth, imageHeight) {
  const scale = Math.max(containerWidth / imageWidth, containerHeight / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;

  return {
    x: (containerWidth - width) / 2,
    y: (containerHeight - height) / 2,
    width,
    height,
  };
}

export default function Login() {
  const navigate = useNavigate();
  const { user, login } = useAuth();

  const sceneRef = useRef(null);
  const imageRef = useRef(null);

  const [email, setEmail] = useState(DEMO_USERS[0].email);
  const [password, setPassword] = useState("demo");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [forgotMessage, setForgotMessage] = useState("");
  const [doorOpen, setDoorOpen] = useState(false);
  const [inside, setInside] = useState(!branding.showEntranceScene);

  const [doorStyle, setDoorStyle] = useState({
    "--door-left": "42.4%",
    "--door-top": "33.3%",
    "--door-width": "16.5%",
    "--door-height": "54.5%",
    "--door-cx": "50%",
    "--door-cy": "58%",
    "--cover-width": "100vw",
    "--cover-height": "100vh",
    "--left-bg-x": "0px",
    "--right-bg-x": "0px",
    "--bg-y": "0px",
  });

  const selectedUser = useMemo(() => {
    return DEMO_USERS.find((item) => item.email === email) || {
      label: "User",
      desc: "Yetki ana admin tarafından belirlenir",
    };
  }, [email]);

  useEffect(() => {
    function updateDoorBox() {
      const scene = sceneRef.current;
      const image = imageRef.current;

      if (!scene || !image || !image.naturalWidth || !image.naturalHeight) return;

      const rect = scene.getBoundingClientRect();

      const cover = getCoverRect(
        rect.width,
        rect.height,
        image.naturalWidth,
        image.naturalHeight
      );

      const left = cover.x + cover.width * DOOR_ON_IMAGE.left;
      const top = cover.y + cover.height * DOOR_ON_IMAGE.top;
      const width = cover.width * DOOR_ON_IMAGE.width;
      const height = cover.height * DOOR_ON_IMAGE.height;

      const leftPanelBgX = cover.x - left;
      const rightPanelBgX = cover.x - (left + width / 2);
      const bgY = cover.y - top;

      setDoorStyle({
        "--door-left": `${left}px`,
        "--door-top": `${top}px`,
        "--door-width": `${width}px`,
        "--door-height": `${height}px`,
        "--door-cx": `${left + width / 2}px`,
        "--door-cy": `${top + height / 2}px`,
        "--cover-width": `${cover.width}px`,
        "--cover-height": `${cover.height}px`,
        "--left-bg-x": `${leftPanelBgX}px`,
        "--right-bg-x": `${rightPanelBgX}px`,
        "--bg-y": `${bgY}px`,
      });
    }

    updateDoorBox();

    const image = imageRef.current;
    image?.addEventListener("load", updateDoorBox);
    window.addEventListener("resize", updateDoorBox);

    return () => {
      image?.removeEventListener("load", updateDoorBox);
      window.removeEventListener("resize", updateDoorBox);
    };
  }, []);

  if (user) return <Navigate to="/" replace />;

  function openDoor() {
    if (doorOpen) return;

    setError("");
    setForgotMessage("");
    setDoorOpen(true);

    window.setTimeout(() => {
      setInside(true);
    }, 1280);
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    setForgotMessage("");

    const cleanEmail = String(email || "").trim().toLowerCase();

    if (!cleanEmail || !cleanEmail.includes("@")) {
      setError("Geçerli bir kullanıcı adı / e-posta girin.");
      return;
    }

    if (!password) {
      setError("Şifre alanı boş bırakılamaz.");
      return;
    }

    try {
      if (remember) {
        localStorage.setItem("opex_remember_user", cleanEmail);
      }

      await login(cleanEmail);
      navigate("/");
    } catch (err) {
      setError(err.message || "Giriş yapılamadı.");
    }
  }

  function forgotPassword() {
    setError("");
    setForgotMessage(
      "Şifre sıfırlama akışı canlı ortamda SSO / şirket kimliği üzerinden bağlanacak."
    );
  }

  return (
    <main className={`ym-real-login ${doorOpen ? "door-open" : ""} ${inside ? "inside" : "outside"}`}>
      <AnimatePresence mode="wait">
        {branding.showEntranceScene && !inside ? (
          <motion.section
            key="outside"
            ref={sceneRef}
            className="ym-real-scene"
            style={doorStyle}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            <img
              ref={imageRef}
              className="ym-real-image"
              src={branding.loginImage}
              alt="EAY OneOps operasyon platformu"
            />

            <button
              type="button"
              className="ym-real-door-hitbox"
              onClick={openDoor}
              aria-label="Kapıyı aç"
            />

            <div className="ym-real-door-panels" aria-hidden="true">
              <div className="ym-real-door-panel left" />
              <div className="ym-real-door-panel right" />
              <div className="ym-real-door-shadow" />
            </div>

            <div className="ym-real-tunnel" aria-hidden="true" />
          </motion.section>
        ) : (
          <motion.section
            key="inside"
            className="ym-real-inside"
            initial={{ opacity: 0, scale: 1.02, y: 18, filter: "blur(10px)" }}
            animate={{ opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.58, ease: [0.16, 0.86, 0.22, 1] }}
          >
            <div className="ym-real-inside-bg">
              {branding.loginImage ? <img src={branding.loginImage} alt="" /> : null}
            </div>

            <section className="ym-real-layout">
              <motion.section
                className="ym-real-hero"
                initial={{ opacity: 0, x: -26, filter: "blur(10px)" }}
                animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
                transition={{ duration: 0.6, delay: 0.06, ease: [0.16, 0.86, 0.22, 1] }}
              >
                <div className="ym-real-eyebrow">
                  <ShieldCheck size={16} />
                  Yetkili operasyon girişi
                </div>
                {branding.companyName ? (
                  <>
                    <h1>{branding.companyName}</h1>
                    <p>{branding.productName}</p>
                  </>
                ) : (
                  <>
                    <h1>{branding.productName}</h1>
                    <p>{branding.slogan}</p>
                  </>
                )}

                <span>
                  Kullanıcı rolüne göre modüller açılır. Ana admin görünürlüğü,
                  modül adminleri alan erişimlerini yönetir.
                </span>
              </motion.section>

              <motion.section
                className="ym-real-card"
                initial={{ opacity: 0, x: 26, filter: "blur(10px)" }}
                animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
                transition={{ duration: 0.6, delay: 0.16, ease: [0.16, 0.86, 0.22, 1] }}
              >
                <div className="ym-real-card-glare" />

                <div className="ym-real-head">
                  <div className="ym-real-icon">
                    <KeyRound size={24} />
                  </div>

                  <div>
                    <span>Giriş</span>
                    <h2>Kontrol merkezine eriş</h2>
                  </div>
                </div>

                <form onSubmit={submit} className="ym-real-form">
                  <label htmlFor="ym-login-email">Kullanıcı adı / e-posta</label>

                  <div className="ym-real-input">
                    <UserRound size={18} />
                    <input
                      id="ym-login-email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      list="ym-demo-users"
                      autoComplete="username"
                      placeholder="ad.soyad@yemeksepeti.com"
                    />
                  </div>

                  <datalist id="ym-demo-users">
                    {DEMO_USERS.map((demo) => (
                      <option key={demo.email} value={demo.email} />
                    ))}
                  </datalist>

                  <label htmlFor="ym-login-password">Şifre</label>

                  <div className="ym-real-input">
                    <KeyRound size={18} />
                    <input
                      id="ym-login-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      placeholder="Şifrenizi girin"
                    />

                    <button
                      type="button"
                      className="ym-real-eye"
                      onClick={() => setShowPassword((current) => !current)}
                      aria-label={showPassword ? "Şifreyi gizle" : "Şifreyi göster"}
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>

                  <div className="ym-real-options">
                    <label className="ym-real-check">
                      <input
                        type="checkbox"
                        checked={remember}
                        onChange={(e) => setRemember(e.target.checked)}
                      />
                      <span>Beni hatırla</span>
                    </label>

                    <button type="button" onClick={forgotPassword}>
                      Şifremi unuttum
                    </button>
                  </div>

                  <div className="ym-real-user">
                    <strong>{selectedUser.label}</strong>
                    <span>{selectedUser.desc}</span>
                  </div>

                  {error ? <p className="ym-real-error">{error}</p> : null}
                  {forgotMessage ? <p className="ym-real-info">{forgotMessage}</p> : null}

                  <button type="submit" className="ym-real-submit">
                    Giriş yap
                    <ArrowRight size={18} />
                  </button>
                </form>
              </motion.section>
            </section>
          </motion.section>
        )}
      </AnimatePresence>
    </main>
  );
}



