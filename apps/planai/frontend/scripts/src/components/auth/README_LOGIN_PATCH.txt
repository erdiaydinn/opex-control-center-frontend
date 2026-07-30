Kurulum:
1) frontend/src/components/auth klasörü oluştur.
2) PlonagramAuth.jsx ve PlonagramAuth.css dosyalarını bu klasöre koy.
3) App.jsx içine import ekle:
   import PlonagramAuth from "./components/auth/PlonagramAuth";
4) App fonksiyonunda auth state ekle:
   const [isAuthed, setIsAuthed] = useState(localStorage.getItem("plonagram_auth") === "1");
   const [currentUser, setCurrentUser] = useState({
     username: localStorage.getItem("plonagram_user") || "",
     role: localStorage.getItem("plonagram_role") || "USER"
   });
5) return'den önce ekle:
   if (!isAuthed) {
     return <PlonagramAuth onLogin={(u) => { setCurrentUser(u); setIsAuthed(true); }} />;
   }
