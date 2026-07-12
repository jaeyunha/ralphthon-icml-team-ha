import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { auditReadOnlyRouteTable, EXPECTED_GET_ROUTES } from "./route-policy";

const apiRoot = fileURLToPath(new URL("../src/app/api", import.meta.url));

test("viewer exposes exactly the read-only §23 route table", async () => {
  const audit = await auditReadOnlyRouteTable(apiRoot);

  assert.deepEqual(audit.routeFiles, [...EXPECTED_GET_ROUTES]);
  assert.deepEqual(audit.missingRoutes, []);
  assert.deepEqual(audit.unexpectedRoutes, []);
  assert.deepEqual(audit.mutationExports, []);
  assert.deepEqual(audit.missingGetExports, []);
});
