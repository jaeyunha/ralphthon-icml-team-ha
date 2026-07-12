import type {
  PgClient,
  PgPool,
  PgQueryResult,
  PgQueryable,
} from "./postgres-store";

interface PostgresJsResult<TRow extends object> extends Array<TRow> {
  count: number;
}

interface PostgresJsQueryable {
  unsafe<TRow extends object = Record<string, unknown>>(
    query: string,
    parameters?: readonly unknown[],
  ): Promise<PostgresJsResult<TRow>>;
}

interface PostgresJsReserved extends PostgresJsQueryable {
  release(): void | Promise<void>;
}

export interface PostgresJsSql extends PostgresJsQueryable {
  reserve(): Promise<PostgresJsReserved>;
}

export interface PostgresJsPoolOptions {
  serializeJsonParameters?: boolean;
}

function serializeParameter(value: unknown): unknown {
  if (value === null || value instanceof Date || value instanceof Uint8Array) {
    return value;
  }
  return typeof value === "object" ? JSON.stringify(value) : value;
}

function wrapQueryable(
  queryable: PostgresJsQueryable,
  options: PostgresJsPoolOptions,
): PgQueryable {
  return {
    async query<TRow extends object = Record<string, unknown>>(
      text: string,
      values: readonly unknown[] = [],
    ): Promise<PgQueryResult<TRow>> {
      const parameters = options.serializeJsonParameters
        ? values.map(serializeParameter)
        : values;
      const result = await queryable.unsafe<TRow>(text, parameters);
      return { rows: Array.from(result), rowCount: result.count };
    },
  };
}

export function createPostgresJsPool(
  sql: PostgresJsSql,
  options: PostgresJsPoolOptions = {},
): PgPool {
  const pool = wrapQueryable(sql, options);
  return {
    ...pool,
    async connect(): Promise<PgClient> {
      const reserved = await sql.reserve();
      return {
        ...wrapQueryable(reserved, options),
        release() {
          void reserved.release();
        },
      };
    },
  };
}
