import { readdir, readFile } from "node:fs/promises";
import { join, relative, sep } from "node:path";

export const EXPECTED_GET_ROUTES = [
  "api/runs/[runId]/artifacts/[artifactId]/route.ts",
  "api/runs/[runId]/audit/export/route.ts",
  "api/runs/[runId]/events/route.ts",
  "api/runs/[runId]/events/stream/route.ts",
  "api/runs/[runId]/notes/route.ts",
  "api/runs/[runId]/route.ts",
  "api/runs/[runId]/snapshot/route.ts",
  "api/runs/route.ts",
] as const;

const MUTATION_METHOD_EXPORT =
  /\bexport\s+(?:(?:async\s+)?function|const|let|var)\s+(POST|PUT|PATCH|DELETE)\b|\bexport\s*\{[^}]*(POST|PUT|PATCH|DELETE)\b[^}]*\}/s;

export interface RouteAudit {
  routeFiles: string[];
  missingRoutes: string[];
  unexpectedRoutes: string[];
  mutationExports: string[];
  missingGetExports: string[];
}

async function collectRouteFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) return collectRouteFiles(path);
      return entry.isFile() && /^route\.(?:[cm]?js|[jt]sx?)$/.test(entry.name) ? [path] : [];
    }),
  );

  return nested.flat();
}

function hasGetExport(source: string): boolean {
  return (
    /\bexport\s+(?:(?:async\s+)?function|const|let|var)\s+GET\b/.test(source) ||
    /\bexport\s*\{[^}]*\bGET\b[^}]*\}/s.test(source)
  );
}

export async function auditReadOnlyRouteTable(apiRoot: string): Promise<RouteAudit> {
  let absoluteFiles: string[] = [];
  try {
    absoluteFiles = await collectRouteFiles(apiRoot);
  } catch (error) {
    const code = error instanceof Error && "code" in error ? error.code : undefined;
    if (code !== "ENOENT") throw error;
  }

  const routeFiles = absoluteFiles
    .map((file) => `api/${relative(apiRoot, file).split(sep).join("/")}`)
    .sort();
  const expected = [...EXPECTED_GET_ROUTES];
  const missingRoutes = expected.filter((route) => !routeFiles.includes(route));
  const unexpectedRoutes = routeFiles.filter(
    (route) => !EXPECTED_GET_ROUTES.includes(route as (typeof EXPECTED_GET_ROUTES)[number]),
  );
  const mutationExports: string[] = [];
  const missingGetExports: string[] = [];

  await Promise.all(
    absoluteFiles.map(async (file) => {
      const source = await readFile(file, "utf8");
      const route = `api/${relative(apiRoot, file).split(sep).join("/")}`;
      if (MUTATION_METHOD_EXPORT.test(source)) mutationExports.push(route);
      if (!hasGetExport(source)) missingGetExports.push(route);
    }),
  );

  return {
    routeFiles,
    missingRoutes: missingRoutes.sort(),
    unexpectedRoutes: unexpectedRoutes.sort(),
    mutationExports: mutationExports.sort(),
    missingGetExports: missingGetExports.sort(),
  };
}
