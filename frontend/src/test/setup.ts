import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom doesn't implement window.matchMedia at all — useIsMobile.ts (and
// any component that uses it) crashes on render in tests without this.
// Mocked as "never matches" (isMobile: false) by default; individual
// tests can override matches on a per-call basis if they need to
// simulate a mobile viewport specifically.
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});