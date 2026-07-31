import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, isLocale, LOCALES, translator } from "./i18n";

describe("translator", () => {
  it("returns the English key when a locale has no translation for it", () => {
    // The load-bearing property: a missing translation degrades to readable English, never to
    // a key path. In a compliance product an English label is a cosmetic defect; an unreadable
    // one is a user who cannot tell what a control does.
    expect(translator("fr")("a string nobody has translated")).toBe(
      "a string nobody has translated",
    );
    expect(translator("en")("Refresh")).toBe("Refresh");
  });

  it("translates the keys it does have", () => {
    expect(translator("fr")("Refresh")).toBe("Actualiser");
    expect(translator("fr")("Opportunities")).toBe("Opportunités");
  });

  it("keeps {portal} intact so the caller can name the market's own source", () => {
    // Copy that hardcodes "GeM" is a false statement above a feed of TED notices, so the
    // placeholder has to survive translation in every locale.
    for (const locale of LOCALES) {
      expect(translator(locale)("Swept from {portal}")).toContain("{portal}");
    }
  });

  it("recognises exactly the supported locales", () => {
    expect(isLocale("fr")).toBe(true);
    expect(isLocale("de")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
    expect(LOCALES).toContain(DEFAULT_LOCALE);
  });
});
