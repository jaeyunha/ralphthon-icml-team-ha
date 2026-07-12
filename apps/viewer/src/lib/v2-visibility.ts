export type PublicationAudience = "reviewer" | "author" | "committee" | "public";

export interface ProjectedPublicationGrant {
  readonly runId: string;
  readonly publicationId: string;
  readonly eventHash: string;
  readonly receiptHash: string;
  readonly audience: PublicationAudience;
  readonly release: string;
  readonly sanitizedPublic: boolean;
}

export interface PublicationVisibilityRequest {
  readonly runId: string;
  readonly publicationId: string;
  readonly audience: PublicationAudience;
  readonly release: string;
  readonly eventHash?: string;
  readonly receiptHash?: string;
}

export interface VisiblePublication {
  readonly publicationId: string;
  readonly eventHash: string;
  readonly receiptHash: string;
  readonly bytes: Uint8Array;
}

const SHA256 = /^sha256:[0-9a-f]{64}$/;

export function authorizeProjectedPublication(
  grants: readonly ProjectedPublicationGrant[],
  request: PublicationVisibilityRequest,
): ProjectedPublicationGrant | null {
  if (!safeIdentifier(request.runId) || !safeIdentifier(request.publicationId) || !safeIdentifier(request.release)) {
    return null;
  }
  const exact = grants.filter(
    (grant) =>
      grant.runId === request.runId &&
      grant.publicationId === request.publicationId &&
      grant.audience === request.audience &&
      grant.release === request.release,
  );
  if (exact.length !== 1) return null;
  const grant = exact[0]!;
  if (!SHA256.test(grant.eventHash) || !SHA256.test(grant.receiptHash)) return null;
  if (request.eventHash !== undefined && request.eventHash !== grant.eventHash) return null;
  if (request.receiptHash !== undefined && request.receiptHash !== grant.receiptHash) return null;
  if (request.audience === "public" && !grant.sanitizedPublic) return null;
  return grant;
}

export function readProjectedPublication(
  grants: readonly ProjectedPublicationGrant[],
  immutableBytesByPublicationId: ReadonlyMap<string, Uint8Array>,
  request: PublicationVisibilityRequest,
): VisiblePublication | null {
  const grant = authorizeProjectedPublication(grants, request);
  if (!grant) return null;
  const bytes = immutableBytesByPublicationId.get(grant.publicationId);
  if (!bytes) return null;
  return {
    publicationId: grant.publicationId,
    eventHash: grant.eventHash,
    receiptHash: grant.receiptHash,
    bytes: bytes.slice(),
  };
}

export function publicAuditGrant(grant: ProjectedPublicationGrant): Readonly<Record<string, unknown>> | null {
  if (grant.audience !== "public" || !grant.sanitizedPublic) return null;
  return Object.freeze({
    run_id: grant.runId,
    publication_id: grant.publicationId,
    event_hash: grant.eventHash,
    receipt_hash: grant.receiptHash,
    audience: grant.audience,
    release: grant.release,
    sanitized_public: true,
  });
}

function safeIdentifier(value: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value) && !value.includes("..") && !value.includes("/");
}
