export type JsonPrimitive = boolean | null | number | string;
export type JsonValue =
  | JsonPrimitive
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

export class CanonicalJsonError extends TypeError {
  constructor(message: string) {
    super(message);
    this.name = "CanonicalJsonError";
  }
}

export function canonicalJson(value: unknown): string {
  return encode(value, new Set<object>(), "$");
}

function encode(value: unknown, ancestors: Set<object>, path: string): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }

  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new CanonicalJsonError(`${path} contains a non-finite number`);
    }
    return JSON.stringify(value);
  }

  if (typeof value !== "object") {
    throw new CanonicalJsonError(`${path} contains unsupported ${typeof value}`);
  }

  if (ancestors.has(value)) {
    throw new CanonicalJsonError(`${path} contains a cycle`);
  }

  ancestors.add(value);
  try {
    if (Array.isArray(value)) {
      return `[${value.map((item, index) => encode(item, ancestors, `${path}[${index}]`)).join(",")}]`;
    }

    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new CanonicalJsonError(`${path} must contain only plain JSON objects`);
    }

    const object = value as Record<string, unknown>;
    const entries = Object.keys(object)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${encode(object[key], ancestors, `${path}.${key}`)}`);
    return `{${entries.join(",")}}`;
  } finally {
    ancestors.delete(value);
  }
}
