export interface JsonSchemaValidationResult {
  valid: boolean;
  errors: string[];
}

type Schema = Record<string, unknown>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function valueType(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (Number.isInteger(value)) return "integer";
  return typeof value;
}

function matchesType(value: unknown, expected: string): boolean {
  if (expected === "object") return isRecord(value);
  if (expected === "array") return Array.isArray(value);
  if (expected === "integer") return Number.isInteger(value);
  if (expected === "number") return typeof value === "number" && Number.isFinite(value);
  if (expected === "null") return value === null;
  return typeof value === expected;
}

function isCalendarDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/u.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function validateNode(value: unknown, schema: Schema, path: string, errors: string[]): void {
  if (Array.isArray(schema.enum) && !schema.enum.some((choice) => Object.is(choice, value))) {
    errors.push(`${path} must be one of ${schema.enum.map(String).join(", ")}`);
    return;
  }
  if (schema.const !== undefined && !Object.is(schema.const, value)) {
    errors.push(`${path} must equal ${String(schema.const)}`);
    return;
  }

  const declaredTypes = Array.isArray(schema.type)
    ? schema.type.filter((item): item is string => typeof item === "string")
    : typeof schema.type === "string"
      ? [schema.type]
      : [];
  if (declaredTypes.length > 0 && !declaredTypes.some((type) => matchesType(value, type))) {
    errors.push(`${path} must be ${declaredTypes.join(" or ")}, received ${valueType(value)}`);
    return;
  }

  if (typeof value === "string") {
    if (typeof schema.minLength === "number" && value.length < schema.minLength) {
      errors.push(`${path} must contain at least ${schema.minLength} characters`);
    }
    if (typeof schema.maxLength === "number" && value.length > schema.maxLength) {
      errors.push(`${path} must contain at most ${schema.maxLength} characters`);
    }
    if (typeof schema.pattern === "string" && !new RegExp(schema.pattern, "u").test(value)) {
      errors.push(`${path} does not match ${schema.pattern}`);
    }
    if (schema.format === "date" && !isCalendarDate(value)) {
      errors.push(`${path} must be an RFC 3339 full-date`);
    }
    if (schema.format === "date-time" && !Number.isFinite(Date.parse(value))) {
      errors.push(`${path} must be an RFC 3339 date-time`);
    }
  }

  if (typeof value === "number") {
    if (typeof schema.minimum === "number" && value < schema.minimum) errors.push(`${path} is below minimum`);
    if (typeof schema.maximum === "number" && value > schema.maximum) errors.push(`${path} is above maximum`);
  }

  if (Array.isArray(value)) {
    if (typeof schema.minItems === "number" && value.length < schema.minItems) {
      errors.push(`${path} must contain at least ${schema.minItems} items`);
    }
    if (schema.uniqueItems === true && new Set(value.map((item) => JSON.stringify(item))).size !== value.length) {
      errors.push(`${path} must contain unique items`);
    }
    if (isRecord(schema.items)) {
      value.forEach((item, index) => validateNode(item, schema.items as Schema, `${path}[${index}]`, errors));
    }
  }

  if (isRecord(value)) {
    const properties = isRecord(schema.properties) ? schema.properties : {};
    const required = Array.isArray(schema.required)
      ? schema.required.filter((item): item is string => typeof item === "string")
      : [];
    for (const key of required) {
      if (!(key in value)) errors.push(`${path}.${key} is required`);
    }
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!(key in properties)) errors.push(`${path}.${key} is not allowed`);
      }
    }
    for (const [key, propertySchema] of Object.entries(properties)) {
      if (key in value && isRecord(propertySchema)) {
        validateNode(value[key], propertySchema, `${path}.${key}`, errors);
      }
    }
  }
}

export function validateJsonSchema(value: unknown, schema: unknown): JsonSchemaValidationResult {
  if (!isRecord(schema)) return { valid: false, errors: ["schema root must be an object"] };
  const errors: string[] = [];
  validateNode(value, schema, "$", errors);
  return { valid: errors.length === 0, errors };
}
