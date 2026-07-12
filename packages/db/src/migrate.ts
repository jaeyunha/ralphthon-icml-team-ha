import { fileURLToPath } from "node:url";
import { migrate } from "drizzle-orm/postgres-js/migrator";

import { createDatabase, databaseUrl } from "./client";

export const defaultMigrationsFolder = fileURLToPath(
  new URL("../../../migrations", import.meta.url),
);

export async function runMigrations(
  url = databaseUrl(),
  migrationsFolder = defaultMigrationsFolder,
): Promise<void> {
  const connection = createDatabase(url, { max: 1 });
  try {
    await migrate(connection.db, { migrationsFolder });
  } finally {
    await connection.close();
  }
}

if (import.meta.main) {
  await runMigrations();
  console.log(`Applied database migrations from ${defaultMigrationsFolder}`);
}
