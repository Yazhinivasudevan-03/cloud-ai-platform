import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// Vitest doesn't auto-run Testing Library's DOM cleanup between tests
// unless `test.globals: true` is set (it isn't here - test files import
// their own vitest globals explicitly instead) - without this, a
// component rendered in one test stays mounted in `document.body` for
// the next test, and a `screen` query can silently match leftover DOM
// from a previous test instead of the current render.
afterEach(() => {
  cleanup();
});
