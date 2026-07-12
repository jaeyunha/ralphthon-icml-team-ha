import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { auditReadOnlyRouteTable, EXPECTED_GET_ROUTES } from "./route-policy";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) =>
      rm(directory, { recursive: true, force: true }),
    ),
  );
});

async function createApiTree(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "viewer-routes-"));
  temporaryDirectories.push(root);
  const apiRoot = join(root, "api");

  await Promise.all(
    EXPECTED_GET_ROUTES.map(async (route) => {
      const file = join(root, route);
      await mkdir(dirname(file), { recursive: true });
      await writeFile(file, "export async function GET() { return new Response(); }\n");
    }),
  );

  return apiRoot;
}

test("accepts the exact GET-only route set", async () => {
  const audit = await auditReadOnlyRouteTable(await createApiTree());

  assert.deepEqual(audit.routeFiles, [...EXPECTED_GET_ROUTES]);
  assert.deepEqual(audit.missingRoutes, []);
  assert.deepEqual(audit.unexpectedRoutes, []);
  assert.deepEqual(audit.mutationExports, []);
  assert.deepEqual(audit.missingGetExports, []);
});

test("reports mutation exports and unexpected routes", async () => {
  const apiRoot = await createApiTree();
  const mutationRoute = join(apiRoot, "runs", "[runId]", "restart", "route.ts");
  await mkdir(dirname(mutationRoute), { recursive: true });
  await writeFile(
    mutationRoute,
    "export const GET = () => new Response();\nexport const POST = () => new Response();\n",
  );

  const audit = await auditReadOnlyRouteTable(apiRoot);

  assert.deepEqual(audit.unexpectedRoutes, ["api/runs/[runId]/restart/route.ts"]);
  assert.deepEqual(audit.mutationExports, ["api/runs/[runId]/restart/route.ts"]);
  const aliasedMutationRoute = join(apiRoot, "runs", "[runId]", "pause", "route.js");
  await mkdir(dirname(aliasedMutationRoute), { recursive: true });
  await writeFile(
    aliasedMutationRoute,
    "const handler = () => new Response();\nexport { handler as GET, handler as POST };\n",
  );

  const aliasedAudit = await auditReadOnlyRouteTable(apiRoot);
  assert.deepEqual(aliasedAudit.unexpectedRoutes, [
    "api/runs/[runId]/pause/route.js",
    "api/runs/[runId]/restart/route.ts",
  ]);
  assert.deepEqual(aliasedAudit.mutationExports, [
    "api/runs/[runId]/pause/route.js",
    "api/runs/[runId]/restart/route.ts",
  ]);
});

test("reports missing routes and handlers", async () => {
  const apiRoot = await createApiTree();
  const missingRoute = join(apiRoot, "runs", "[runId]", "snapshot", "route.ts");
  await rm(missingRoute);
  const eventsRoute = join(apiRoot, "runs", "[runId]", "events", "route.ts");
  await writeFile(eventsRoute, "const handler = () => new Response();\nexport default handler;\n");

  const audit = await auditReadOnlyRouteTable(apiRoot);

  assert.deepEqual(audit.missingRoutes, ["api/runs/[runId]/snapshot/route.ts"]);
  assert.deepEqual(audit.missingGetExports, ["api/runs/[runId]/events/route.ts"]);
});
