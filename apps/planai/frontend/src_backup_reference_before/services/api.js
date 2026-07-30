// PLONAGRAM OS API Service Layer
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001';

class PlonagramAPI {
  async login(email, password, storeCode) {
    return fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, store_code: storeCode })
    }).then(r => r.json());
  }

  async getStores() {
    return fetch(`${API_BASE}/auth/stores`).then(r => r.json());
  }

  async getMasterProducts() {
    return fetch(`${API_BASE}/master-products`).then(r => r.json());
  }

  async generatePlanogram(storeCode) {
    return fetch(`${API_BASE}/generate-planogram`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ store_code: storeCode })
    }).then(r => r.json());
  }

  async getLayout(storeCode) {
    return fetch(`${API_BASE}/core/layouts/${storeCode}`).then(r => r.json());
  }

  async saveLayout(storeCode, layoutData) {
    return fetch(`${API_BASE}/core/layouts/${storeCode}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(layoutData)
    }).then(r => r.json());
  }
}

export const api = new PlonagramAPI();
export default api;
