import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { en, fr, type DictKey } from "./dict";

export type Lang = "fr" | "en";
const KEY = "sd_lang";
const DICTS: Record<Lang, Record<DictKey, string>> = { fr, en };

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "fr" || stored === "en") return stored;
  } catch {
    /* ignore */
  }
  return "fr";
}

export type TFn = (key: DictKey, vars?: Record<string, string | number>) => string;

interface I18nValue { lang: Lang; setLang: (l: Lang) => void; t: TFn; locale: string }
const I18nContext = createContext<I18nValue | null>(null);

export function translate(lang: Lang, key: DictKey, vars?: Record<string, string | number>): string {
  let text = DICTS[lang][key] ?? key;
  if (vars) for (const [name, value] of Object.entries(vars)) text = text.split(`{${name}}`).join(String(value));
  return text;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
  }, []);
  const t = useCallback<TFn>((key, vars) => translate(lang, key, vars), [lang]);
  return (
    <I18nContext.Provider value={{ lang, setLang, t, locale: lang === "fr" ? "fr-FR" : "en-GB" }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
