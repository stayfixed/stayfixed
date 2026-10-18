import { test } from "node:test";
import assert from "node:assert/strict";

test("passes", () => { assert.ok(true); });
test("fails", () => { assert.equal(1, 2); });
test("skipped", { skip: "on purpose" }, () => {});
