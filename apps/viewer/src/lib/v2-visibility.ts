import { sha256Bytes, type Sha256 } from "../../../../packages/contracts/src/hashing";

export type PublicationAudience = "reviewer" | "author" | "committee" | "public";

export interface AuthenticatedAudiencePrincipal {
  readonly audience: PublicationAudience;
  readonly subjectId: string;
  readonly authentication: {
    readonly scheme: "projector-session-v2";
    readonly sessionHash: Sha256;
  };
}

/** Exact row shape returned by the v2 `committed_publications` projection. */
export interface CommittedPublicationRegistryRow {
  readonly run_id: string;
  readonly publication_id: string;
  readonly event_id: string;
  readonly event_hash: string;
  readonly receipt_hash: string;
  readonly content_hash: string;
  readonly sanitization_receipt_hash: string | null;
  readonly audience: string;
  readonly release_status: string;
  readonly sanitization_status: string;
}

export function projectedGrantFromCommittedPublicationRow(
  row: CommittedPublicationRegistryRow,
): ProjectedPublicationGrant | null {
  if (!safeIdentifier(row.run_id) || !safeIdentifier(row.publication_id) || !safeIdentifier(row.event_id)
    || !isHash(row.event_hash) || !isHash(row.receipt_hash) || !isHash(row.content_hash)
    || !isAudience(row.audience) || !safeIdentifier(row.release_status)
    || (row.sanitization_receipt_hash !== null && !isHash(row.sanitization_receipt_hash))
    || (row.audience === "public" && (row.sanitization_status !== "sanitized_public" || row.sanitization_receipt_hash === null))
    || (row.audience !== "public" && row.sanitization_status !== "private")) return null;
  return {
    runId: row.run_id,
    publicationId: row.publication_id,
    eventId: row.event_id,
    eventHash: row.event_hash,
    receiptHash: row.receipt_hash,
    contentHash: row.content_hash,
    audience: row.audience,
    release: row.release_status,
    sanitizationReceiptHash: row.sanitization_receipt_hash,
  };
}

/** Production adapter for authenticated viewer sessions backed by committed projection rows. */
export class CommittedPublicationRegistryAdapter implements ProjectorPublicationRegistryAdapter {
  readonly authority = "projector-v2" as const;
  private readonly grants: readonly ProjectedPublicationGrant[];

  constructor(
    rows: readonly CommittedPublicationRegistryRow[],
    private readonly authenticate: (principal: AuthenticatedAudiencePrincipal, audience: PublicationAudience) => void,
  ) {
    this.grants = rows.flatMap((row) => {
      const grant = projectedGrantFromCommittedPublicationRow(row);
      return grant === null ? [] : [grant];
    });
  }

  findExact(request: PublicationVisibilityRequest): readonly ProjectedPublicationGrant[] {
    return this.grants.filter((grant) => sameGrant(grant, request));
  }

  assertAuthenticatedPrincipal(principal: AuthenticatedAudiencePrincipal, audience: PublicationAudience): void {
    this.authenticate(principal, audience);
  }

  assertTrustedSanitizationReceipt(grant: ProjectedPublicationGrant): void {
    if (grant.audience !== "public" || grant.sanitizationReceiptHash === null
      || !this.grants.some((candidate) => sameGrant(candidate, grant)
        && candidate.sanitizationReceiptHash === grant.sanitizationReceiptHash)) {
      throw new Error("sanitization receipt is not bound to a committed public publication");
    }
  }
}

export interface ProjectedPublicationGrant {
  readonly runId: string;
  readonly publicationId: string;
  readonly eventId: string;
  readonly eventHash: Sha256;
  readonly receiptHash: Sha256;
  readonly contentHash: Sha256;
  readonly audience: PublicationAudience;
  readonly release: string;
  readonly sanitizationReceiptHash: Sha256 | null;
}

export interface PublicationVisibilityRequest {
  readonly runId: string;
  readonly publicationId: string;
  readonly audience: PublicationAudience;
  readonly release: string;
  readonly eventId: string;
  readonly eventHash: Sha256;
  readonly receiptHash: Sha256;
  readonly contentHash: Sha256;
}

export interface ProjectorPublicationRegistryAdapter {
  readonly authority: "projector-v2";
  findExact(request: PublicationVisibilityRequest): readonly ProjectedPublicationGrant[];
  assertAuthenticatedPrincipal(principal: AuthenticatedAudiencePrincipal, audience: PublicationAudience): void;
  assertTrustedSanitizationReceipt(grant: ProjectedPublicationGrant): void;
}

export interface VisiblePublication {
  readonly runId: string;
  readonly publicationId: string;
  readonly eventId: string;
  readonly eventHash: Sha256;
  readonly receiptHash: Sha256;
  readonly contentHash: Sha256;
  readonly bytes: Uint8Array;
}

export function publicationProvenanceKey(provenance: PublicationVisibilityRequest): string {
  return [
    provenance.runId,
    provenance.publicationId,
    provenance.eventId,
    provenance.eventHash,
    provenance.receiptHash,
    provenance.contentHash,
    provenance.audience,
    provenance.release,
  ].join("\u0000");
}

export function authorizeProjectedPublication(
  registry: ProjectorPublicationRegistryAdapter,
  principal: AuthenticatedAudiencePrincipal,
  request: PublicationVisibilityRequest,
): ProjectedPublicationGrant | null {
  if (registry.authority !== "projector-v2" || !validRequest(request) || !validPrincipal(principal) || principal.audience !== request.audience) return null;
  try {
    registry.assertAuthenticatedPrincipal(principal, request.audience);
    const grants = registry.findExact(request);
    if (grants.length !== 1) return null;
    const grant = grants[0]!;
    if (!sameGrant(grant, request)) return null;
    if (request.audience === "public") {
      if (grant.sanitizationReceiptHash === null) return null;
      registry.assertTrustedSanitizationReceipt(grant);
    }
    return grant;
  } catch {
    return null;
  }
}

export function readProjectedPublication(
  registry: ProjectorPublicationRegistryAdapter,
  immutableBytesByProvenance: ReadonlyMap<string, Uint8Array>,
  principal: AuthenticatedAudiencePrincipal,
  request: PublicationVisibilityRequest,
): VisiblePublication | null {
  const grant = authorizeProjectedPublication(registry, principal, request);
  if (!grant) return null;
  const bytes = immutableBytesByProvenance.get(publicationProvenanceKey(request));
  if (!bytes || sha256Bytes(bytes) !== grant.contentHash) return null;
  return {
    runId: grant.runId,
    publicationId: grant.publicationId,
    eventId: grant.eventId,
    eventHash: grant.eventHash,
    receiptHash: grant.receiptHash,
    contentHash: grant.contentHash,
    bytes: bytes.slice(),
  };
}

export function publicAuditGrant(
  registry: ProjectorPublicationRegistryAdapter,
  grant: ProjectedPublicationGrant,
): Readonly<Record<string, unknown>> | null {
  if (registry.authority !== "projector-v2" || grant.audience !== "public" || grant.sanitizationReceiptHash === null) return null;
  try {
    registry.assertTrustedSanitizationReceipt(grant);
  } catch {
    return null;
  }
  return Object.freeze({
    run_id: grant.runId,
    publication_id: grant.publicationId,
    event_id: grant.eventId,
    event_hash: grant.eventHash,
    receipt_hash: grant.receiptHash,
    content_hash: grant.contentHash,
    sanitization_receipt_hash: grant.sanitizationReceiptHash,
    audience: grant.audience,
    release: grant.release,
  });
}

function sameGrant(grant: ProjectedPublicationGrant, request: PublicationVisibilityRequest): boolean {
  return grant.runId === request.runId && grant.publicationId === request.publicationId && grant.eventId === request.eventId
    && grant.eventHash === request.eventHash && grant.receiptHash === request.receiptHash && grant.contentHash === request.contentHash
    && grant.audience === request.audience && grant.release === request.release;
}

function validRequest(request: PublicationVisibilityRequest): boolean {
  return safeIdentifier(request.runId) && safeIdentifier(request.publicationId) && safeIdentifier(request.eventId)
    && safeIdentifier(request.release) && isHash(request.eventHash) && isHash(request.receiptHash) && isHash(request.contentHash);
}

function validPrincipal(principal: AuthenticatedAudiencePrincipal): boolean {
  return safeIdentifier(principal.subjectId) && principal.authentication.scheme === "projector-session-v2" && isHash(principal.authentication.sessionHash);
}

function isHash(value: string): value is Sha256 {
  return /^sha256:[0-9a-f]{64}$/.test(value);
}

function isAudience(value: string): value is PublicationAudience {
  return value === "reviewer" || value === "author" || value === "committee" || value === "public";
}

function safeIdentifier(value: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value) && !value.includes("..") && !value.includes("/");
}
