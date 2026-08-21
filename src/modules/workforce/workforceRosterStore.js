const DB_NAME = "opex-workforce";
const STORE_NAME = "roster";
const KEY = "current-roster";

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function transaction(mode, callback) {
  if (typeof window === "undefined" || !window.indexedDB) return null;
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = database.transaction(STORE_NAME, mode);
    const store = tx.objectStore(STORE_NAME);
    const request = callback(store);
    request.onsuccess = () => resolve(request.result ?? null);
    request.onerror = () => reject(request.error);
    tx.oncomplete = () => database.close();
  });
}

export function loadRosterRows() { return transaction("readonly", (store) => store.get(KEY)).then((value) => value || []); }
export function saveRosterRows(rows) { return transaction("readwrite", (store) => store.put(rows, KEY)); }
export function clearRosterRows() { return transaction("readwrite", (store) => store.delete(KEY)); }
