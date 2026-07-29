import { useEffect, useMemo, useReducer } from "react";
import { plonagramApi } from "../services/plonagramApi";

const initialState = {
  storeCode: null,
  store: null,
  dna: null,
  layout: null,
  objectLibrary: null,
  capacity: null,
  route: null,
  loading: false,
  error: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "loading": return { ...state, loading: true, error: null };
    case "error": return { ...state, loading: false, error: action.error };
    case "setStore": return { ...state, storeCode: action.storeCode, store: action.store };
    case "setDNA": return { ...state, dna: action.dna };
    case "setLayout": return { ...state, layout: action.layout };
    case "setObjectLibrary": return { ...state, objectLibrary: action.objectLibrary };
    case "setScores": return { ...state, capacity: action.capacity ?? state.capacity, route: action.route ?? state.route, loading: false };
    case "ready": return { ...state, loading: false };
    default: return state;
  }
}

export function usePlonagramCore() {
  const [state, dispatch] = useReducer(reducer, initialState);

  async function loadStore(storeCode) {
    dispatch({ type: "loading" });
    try {
      const [storeRes, dnaRes, layoutRes, objRes] = await Promise.all([
        plonagramApi.getStore(storeCode),
        plonagramApi.getDepotDNA(storeCode),
        plonagramApi.getLayout(storeCode),
        plonagramApi.getObjectLibrary(),
      ]);
      dispatch({ type: "setStore", storeCode, store: storeRes.store });
      dispatch({ type: "setDNA", dna: dnaRes.dna });
      dispatch({ type: "setLayout", layout: layoutRes.layout });
      dispatch({ type: "setObjectLibrary", objectLibrary: objRes.library });
      dispatch({ type: "ready" });
    } catch (err) {
      dispatch({ type: "error", error: err.message });
    }
  }

  async function saveDNA(nextDNA) {
    if (!state.storeCode) throw new Error("storeCode yok");
    const res = await plonagramApi.saveDepotDNA(state.storeCode, nextDNA);
    dispatch({ type: "setDNA", dna: res.dna });
    return res.dna;
  }

  async function saveLayout(nextLayout) {
    if (!state.storeCode) throw new Error("storeCode yok");
    const res = await plonagramApi.saveLayout(state.storeCode, nextLayout);
    dispatch({ type: "setLayout", layout: res.layout });
    return res.layout;
  }

  async function refreshScores(layout = state.layout) {
    if (!layout) return;
    const [cap, route] = await Promise.all([
      plonagramApi.scoreCapacity(layout),
      plonagramApi.scoreRoute(layout),
    ]);
    dispatch({ type: "setScores", capacity: cap.capacity, route: route.route });
  }

  return useMemo(() => ({
    ...state,
    loadStore,
    saveDNA,
    saveLayout,
    refreshScores,
  }), [state]);
}