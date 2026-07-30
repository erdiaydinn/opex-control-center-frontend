import { useEffect, useRef } from "react";
import { PLG_LANGUAGE_STORAGE_KEY, textMap } from "./globalTextMap";
import "./GlobalTypography.css";

function currentLang() { return localStorage.getItem(PLG_LANGUAGE_STORAGE_KEY) || "tr"; }

function reverseLookup(text) {
  const raw = String(text || "").trim();
  if (!raw) return raw;
  for (const dict of Object.values(textMap)) {
    for (const [key, val] of Object.entries(dict || {})) {
      if (raw === key || raw === val) return key;
    }
  }
  return raw;
}

function translateText(text, lang) {
  const raw = String(text || "");
  const trimmed = raw.trim();
  if (!trimmed) return raw;
  const key = reverseLookup(trimmed);
  if (lang === "tr") return key;
  const enValue = textMap.en?.[key];
  const translated = textMap[lang]?.[key] || (enValue ? textMap[lang]?.[enValue] : null) || (lang === "en" ? enValue : null);
  return translated || trimmed;
}

function skipTextNode(node) {
  const parent = node.parentElement;
  if (!parent) return true;
  if (["SCRIPT","STYLE","TEXTAREA","CODE","PRE"].includes(parent.tagName)) return true;
  if (parent.closest("[data-no-i18n]")) return true;
  return false;
}

function apply(root, lang) {
  if (!root) return;
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (skipTextNode(node)) return NodeFilter.FILTER_REJECT;
      const t = node.nodeValue?.trim();
      if (!t || t.length > 220 || /^[\d\s%.,:;\-/+]+$/.test(t)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const original = node.__plgOriginal || reverseLookup(node.nodeValue);
    node.__plgOriginal = original;
    const next = translateText(original, lang);
    if (next && node.nodeValue.trim() !== next) node.nodeValue = node.nodeValue.replace(node.nodeValue.trim(), next);
  }

  root.querySelectorAll?.("input[placeholder], textarea[placeholder]").forEach((el) => {
    const original = el.dataset.plgOriginalPlaceholder || reverseLookup(el.getAttribute("placeholder"));
    el.dataset.plgOriginalPlaceholder = original;
    el.setAttribute("placeholder", translateText(original, lang));
  });
  root.querySelectorAll?.("option").forEach((el) => {
    const original = el.dataset.plgOriginalText || reverseLookup(el.textContent);
    el.dataset.plgOriginalText = original;
    el.textContent = translateText(original, lang);
  });
}

export default function GlobalTextTranslator() {
  const observer = useRef(null);
  useEffect(() => {
    let raf = null;
    const run = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => apply(document.body, currentLang()));
    };
    run();
    observer.current = new MutationObserver(run);
    observer.current.observe(document.body, { childList:true, subtree:true, characterData:true });
    window.addEventListener("plg:language-changed", run);
    window.addEventListener("storage", run);
    const interval = setInterval(run, 1000);
    return () => { observer.current?.disconnect(); window.removeEventListener("plg:language-changed", run); window.removeEventListener("storage", run); clearInterval(interval); if (raf) cancelAnimationFrame(raf); };
  }, []);
  return null;
}
