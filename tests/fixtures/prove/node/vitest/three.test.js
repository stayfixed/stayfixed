import { test, expect } from "vitest";

test("passes", () => { expect(true).toBe(true); });
test("fails", () => { expect(1).toBe(2); });
test.skip("skipped", () => {});
