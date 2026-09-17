import { describe, expect, it } from "vitest";
import { isValidatedLanguage, languageDisplayName } from "./languages";

describe("languageDisplayName", () => {
  it("maps a known code to its display name", () => {
    expect(languageDisplayName("en")).toBe("English");
    expect(languageDisplayName("ur")).toBe("Urdu");
    expect(languageDisplayName("hi")).toBe("Hindi");
  });

  it("falls back to the uppercased code for an unmapped language", () => {
    expect(languageDisplayName("zz")).toBe("ZZ");
  });
});

describe("isValidatedLanguage", () => {
  it("returns true only for the three languages Sec 3.1 actually tested", () => {
    expect(isValidatedLanguage("en")).toBe(true);
    expect(isValidatedLanguage("ur")).toBe(true);
    expect(isValidatedLanguage("hi")).toBe(true);
  });

  it("returns false for any other language, including ones with display names", () => {
    expect(isValidatedLanguage("fr")).toBe(false);
    expect(isValidatedLanguage("ar")).toBe(false);
  });
});
