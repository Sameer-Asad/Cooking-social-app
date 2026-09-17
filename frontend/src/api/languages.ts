// Sec 3.1: only en/ur/hi are validated; anything else is unverified.
// Display names cover the validated three plus a few common others the
// bot may still be asked in — falls back to the raw code otherwise.
const LANGUAGE_NAMES: Record<string, string> = {
  en: "English",
  ur: "Urdu",
  hi: "Hindi",
  ar: "Arabic",
  fr: "French",
  es: "Spanish",
  bn: "Bengali",
  pa: "Punjabi",
  fa: "Persian",
  tr: "Turkish",
  zh: "Chinese",
};

const VALIDATED_LANGUAGES = new Set(["en", "ur", "hi"]);

export function languageDisplayName(code: string): string {
  return LANGUAGE_NAMES[code] ?? code.toUpperCase();
}

export function isValidatedLanguage(code: string): boolean {
  return VALIDATED_LANGUAGES.has(code);
}
