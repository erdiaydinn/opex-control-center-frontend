# Plonagram Auth Patch

## Frontend bağlama
1. `PlonagramAuth.jsx` dosyasını `frontend/src/components/PlonagramAuth.jsx` olarak koy.
2. `App.jsx` içinde auth state oluştur:

```jsx
import PlonagramAuth from "./components/PlonagramAuth";

export default function App() {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem("plonagram_user") || "null"); }
    catch { return null; }
  });

  if (!user) return <PlonagramAuth onAuthenticated={setUser} />;

  return <YourExistingApp user={user} />;
}
```

## Backend bağlama
1. `auth_routes.py` dosyasını backend klasörüne koy.
2. `main.py` içine ekle:

```python
from auth_routes import router as auth_router
app.include_router(auth_router)
```

Production için demo USERS yerine DB ve gerçek SMTP kullanılmalı.
