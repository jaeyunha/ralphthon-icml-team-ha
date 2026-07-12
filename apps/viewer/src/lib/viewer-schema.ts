import Ajv2020, { type ErrorObject, type ValidateFunction } from "ajv/dist/2020";
import addFormats from "ajv-formats";
import type { EventEnvelope, FinalReview, OfficialReview } from "@ralph-review/schemas";
import eventEnvelopeSchema from "@ralph-review/schemas/schemas/event-envelope.schema.json";
import finalReviewSchema from "@ralph-review/schemas/schemas/final-review.schema.json";
import officialReviewSchema from "@ralph-review/schemas/schemas/official-review.schema.json";

export type PublishedSchemaName = "event-envelope" | "final-review" | "official-review";

export interface PublishedSchemaTypes {
  "event-envelope": EventEnvelope;
  "final-review": FinalReview;
  "official-review": OfficialReview;
}

export class ViewerSchemaError extends Error {
  constructor(
    readonly schemaName: PublishedSchemaName,
    readonly validationErrors: ErrorObject[],
  ) {
    super(`${schemaName} failed frozen schema validation: ${formatErrors(validationErrors)}`);
    this.name = "ViewerSchemaError";
  }
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);

const validators: { [Name in PublishedSchemaName]: ValidateFunction<PublishedSchemaTypes[Name]> } = {
  "event-envelope": ajv.compile<EventEnvelope>(eventEnvelopeSchema),
  "final-review": ajv.compile<FinalReview>(finalReviewSchema),
  "official-review": ajv.compile<OfficialReview>(officialReviewSchema),
};

export function validatePublishedArtifact<Name extends PublishedSchemaName>(
  schemaName: Name,
  value: unknown,
): PublishedSchemaTypes[Name] {
  const validate = validators[schemaName];
  if (!validate(value)) {
    throw new ViewerSchemaError(schemaName, validate.errors ? [...validate.errors] : []);
  }
  return value;
}

function formatErrors(errors: ErrorObject[]): string {
  if (!errors.length) return "unknown validation failure";
  return errors
    .map((error) => `${error.instancePath || "/"} ${error.message ?? error.keyword}`)
    .join("; ");
}
