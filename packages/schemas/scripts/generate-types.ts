import { readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

interface JsonSchema {
  title?: string;
  $id?: string;
  $ref?: string;
  const?: unknown;
  enum?: unknown[];
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  additionalProperties?: boolean | JsonSchema;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  allOf?: JsonSchema[];
}

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schemaDirectory = join(packageRoot, "schemas");
const outputPath = join(packageRoot, "generated", "index.ts");
const checkOnly = process.argv.includes("--check");
const referencedTypeNames = new Map<string, string>();

function literal(value: unknown): string {
  if (typeof value === "string") return JSON.stringify(value);
  if (value === null || typeof value === "number" || typeof value === "boolean") return String(value);
  return "unknown";
}

function renderObject(schema: JsonSchema, depth: number): string {
  const properties = schema.properties ?? {};
  const names = Object.keys(properties).sort();
  const required = new Set(schema.required ?? []);
  const indent = "  ".repeat(depth);
  const childIndent = "  ".repeat(depth + 1);
  const lines = names.map((name) => {
    const optional = required.has(name) ? "" : "?";
    return `${childIndent}${JSON.stringify(name)}${optional}: ${renderType(properties[name]!, depth + 1)};`;
  });

  if (schema.additionalProperties && typeof schema.additionalProperties === "object") {
    lines.push(`${childIndent}[key: string]: ${renderType(schema.additionalProperties, depth + 1)};`);
  } else if (names.length === 0 && schema.additionalProperties !== false) {
    return "Record<string, unknown>";
  }

  return lines.length === 0 ? "Record<string, never>" : `{\n${lines.join("\n")}\n${indent}}`;
}

function renderType(schema: JsonSchema, depth = 0): string {
  if (schema.$ref) return referencedTypeNames.get(schema.$ref) ?? "unknown";
  if (Object.hasOwn(schema, "const")) return literal(schema.const);
  if (schema.enum) return schema.enum.map(literal).join(" | ");
  if (schema.oneOf) return schema.oneOf.map((item) => renderType(item, depth)).join(" | ");
  if (schema.anyOf) return schema.anyOf.map((item) => renderType(item, depth)).join(" | ");

  if (Array.isArray(schema.type)) {
    return schema.type.map((type) => renderType({ ...schema, type }, depth)).join(" | ");
  }

  switch (schema.type) {
    case "null":
      return "null";
    case "boolean":
      return "boolean";
    case "integer":
    case "number":
      return "number";
    case "string":
      return "string";
    case "array":
      return `Array<${renderType(schema.items ?? {}, depth)}>`;
    case "object":
      return renderObject(schema, depth);
    default:
      if (schema.properties || schema.additionalProperties !== undefined) return renderObject(schema, depth);
      return "unknown";
  }
}

const filenames = (await readdir(schemaDirectory))
  .filter((name) => name.endsWith(".schema.json"))
  .sort();

const schemaDocuments = new Map<string, JsonSchema>();
for (const filename of filenames) {
  const schema = JSON.parse(await readFile(join(schemaDirectory, filename), "utf8")) as JsonSchema;
  if (!schema.title) throw new Error(`${filename} must declare a title`);
  schemaDocuments.set(filename, schema);
  referencedTypeNames.set(filename, schema.title);
  if (schema.$id) referencedTypeNames.set(schema.$id, schema.title);
}

const declarations: string[] = [];
for (const schema of schemaDocuments.values()) {
  declarations.push(`export type ${schema.title} = ${renderType(schema)};`);
}

const output = [
  "// Generated from JSON Schema. Do not edit by hand.",
  "// Run `bun run generate:types` from packages/schemas.",
  "",
  ...declarations.flatMap((declaration) => [declaration, ""]),
].join("\n");

if (checkOnly) {
  const current = await readFile(outputPath, "utf8").catch(() => "");
  if (current !== output) {
    console.error("generated/index.ts is out of date; run `bun run generate:types`");
    process.exit(1);
  }
} else {
  await writeFile(outputPath, output);
}
