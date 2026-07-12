import { drizzle, type PostgresJsDatabase } from "drizzle-orm/postgres-js";
import postgres, { type Sql } from "postgres";

import * as schema from "./schema";

export type Database = PostgresJsDatabase<typeof schema>;

export interface DatabaseConnection {
  db: Database;
  client: Sql;
  close: () => Promise<void>;
}

export interface DatabaseConnectionOptions {
  max?: number;
  prepare?: boolean;
}

export function databaseUrl(): string {
  const value = process.env.DATABASE_URL;
  if (!value) {
    throw new Error("DATABASE_URL is required");
  }
  return value;
}

export function createDatabase(
  url = databaseUrl(),
  options: DatabaseConnectionOptions = {},
): DatabaseConnection {
  const client = postgres(url, {
    max: options.max ?? 10,
    prepare: options.prepare ?? true,
  });
  const db = drizzle(client, { schema });

  return {
    db,
    client,
    close: async () => {
      await client.end();
    },
  };
}
