// Translation dictionaries for landing pages
import en from './en';
import zh from './zh';

export const languages = {
  en: 'English',
  zh: '中文',
} as const;

export type Lang = keyof typeof languages;

export const defaultLang: Lang = 'en';

// All language dictionaries — add a new language here
const dicts = { en, zh } as const;

type SectionKey = keyof typeof en;

// Transpose: { en: { hero: ... }, zh: { hero: ... } } → { hero: { en: ..., zh: ... } }
export const translations = Object.fromEntries(
  (Object.keys(en) as SectionKey[]).map(key => [
    key,
    Object.fromEntries(
      (Object.keys(dicts) as Lang[]).map(lang => [lang, dicts[lang][key]])
    ),
  ])
) as Record<SectionKey, Record<Lang, typeof en[SectionKey]>>;

type TranslationsForLang = { lang: Lang } & { [K in SectionKey]: typeof en[K] };

// Helper function to get translations for a language
export function getTranslations(lang: Lang): TranslationsForLang {
  return {
    lang,
    ...Object.fromEntries(
      (Object.keys(en) as SectionKey[]).map(key => [key, translations[key][lang]])
    ),
  } as TranslationsForLang;
}

// Helper to get language from URL path
export function getLangFromUrl(url: string): Lang {
  const [, lang] = url.split('/');
  if ((Object.keys(dicts) as Lang[]).includes(lang as Lang)) return lang as Lang;
  return defaultLang;
}

// Helper to get localized path
export function getLocalizedPath(path: string, lang: Lang): string {
  if (path.startsWith('/')) {
    return `/${lang}${path === '/' ? '' : path}`;
  }
  return path;
}
