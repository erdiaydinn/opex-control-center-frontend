# Plonagram Auth + Store + Approval Patch

## Dosyaları koy
- `frontend/src/components/auth/PlonagramAuth.jsx`
- `frontend/src/components/auth/PlonagramAuth.css`
- `frontend/src/components/auth/PlonagramOperationHero.jsx`
- `frontend/src/components/auth/PlonagramOperationHero.css`
- `backend/auth_routes.py`
- `backend/data/stores.json`
- `backend/main.py`

## Backend
```bash
cd backend
venv\Scripts\activate
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## Test
- `GET http://127.0.0.1:8001/auth/stores`
- Demo admin: `erdi` / `1234`

## Kayıt akışı
- USER: otomatik aktif
- ADMIN / SUPER_USER / STORE_MANAGER / REGIONAL_MANAGER: PENDING_APPROVAL

## Onay endpoint
`POST /auth/approve-user`
```json
{
  "email": "user@company.com",
  "approve": true,
  "approved_by": "erdi"
}
```
