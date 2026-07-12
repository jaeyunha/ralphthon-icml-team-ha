import { defineConfig } from "drizzle-kit";

export default defineConfig({
  dialect: "postgresql",
  schema: "./src/schema.ts",
  out: "../../migrations",
  dbCredentials: {
    url:
      process.env.DATABASE_URL ??
      "postgres://ralph:ralph@localhost:5432/ralph_review",
  },
  strict: true,
  verbose: true,
});
