import type { DiscoveryCandidate, VerifiedSource } from "./types";
import { isBlockedSourceUri, verifyCandidateShape, verifyCanonicalPage } from "./identity";

export interface RetrievalOptions {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  maxBytes?: number;
}

export class RetrievalError extends Error {
  constructor(
    message: string,
    readonly kind: "identity" | "network" | "size" | "content",
  ) {
    super(message);
    this.name = "RetrievalError";
  }
}

function timeoutSignal(timeoutMs: number): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return { signal: controller.signal, clear: () => clearTimeout(timer) };
}

async function fetchBytes(
  fetchImpl: typeof fetch,
  uri: string,
  timeoutMs: number,
  maxBytes: number,
): Promise<{ bytes: Uint8Array; contentType: string; finalUri: string }> {
  if (isBlockedSourceUri(uri)) {
    throw new RetrievalError("retrieval URI is invalid or blocked", "identity");
  }
  const timeout = timeoutSignal(timeoutMs);
  try {
    const response = await fetchImpl(uri, {
      signal: timeout.signal,
      redirect: "follow",
      headers: {
        Accept: "application/pdf,text/html,application/xhtml+xml,text/plain,application/xml;q=0.9,*/*;q=0.1",
        "User-Agent": "ralph-literature-broker/0.1 (+controlled scholarly retrieval)",
      },
    });
    if (!response.ok) {
      throw new RetrievalError(`retrieval returned HTTP ${response.status}`, "network");
    }
    if (isBlockedSourceUri(response.url || uri)) {
      throw new RetrievalError("retrieval redirected to a blocked source", "identity");
    }
    const declaredLength = Number(response.headers.get("content-length") ?? "0");
    if (declaredLength > maxBytes) {
      throw new RetrievalError(`retrieved content exceeds ${maxBytes} bytes`, "size");
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength === 0) {
      throw new RetrievalError("retrieved content is empty", "content");
    }
    if (bytes.byteLength > maxBytes) {
      throw new RetrievalError(`retrieved content exceeds ${maxBytes} bytes`, "size");
    }
    return {
      bytes,
      contentType: response.headers.get("content-type") ?? "application/octet-stream",
      finalUri: response.url || uri,
    };
  } catch (error) {
    if (error instanceof RetrievalError) throw error;
    const message = error instanceof Error ? error.message : String(error);
    throw new RetrievalError(`retrieval failed: ${message}`, "network");
  } finally {
    timeout.clear();
  }
}

function decodeText(bytes: Uint8Array, contentType: string): string {
  if (/pdf|octet-stream/i.test(contentType)) return "";
  return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
}

export async function verifyAndRetrieve(
  candidate: DiscoveryCandidate,
  options: RetrievalOptions = {},
): Promise<VerifiedSource> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? 20_000;
  const maxBytes = options.maxBytes ?? 25 * 1024 * 1024;
  const shape = verifyCandidateShape(candidate);
  if (!shape.verified || !candidate.firstPublicDate) {
    throw new RetrievalError(shape.reason ?? "candidate identity is incomplete", "identity");
  }

  const canonical = await fetchBytes(fetchImpl, candidate.canonicalUri, timeoutMs, Math.min(maxBytes, 5 * 1024 * 1024));
  const canonicalText = decodeText(canonical.bytes, canonical.contentType);
  const directApiText = candidate.backend === "arxiv" || candidate.backend === "crossref" ? candidate.rawContent ?? "" : "";
  const identity = verifyCanonicalPage(candidate, canonicalText || directApiText, canonical.finalUri);
  if (!identity.verified) {
    throw new RetrievalError(identity.reason ?? "source identity could not be verified", "identity");
  }

  const retrievalUri = candidate.fullTextUri ?? candidate.canonicalUri;
  const retrieved = retrievalUri === candidate.canonicalUri
    ? canonical
    : await fetchBytes(fetchImpl, retrievalUri, timeoutMs, maxBytes);
  const verifiedText = decodeText(retrieved.bytes, retrieved.contentType) || canonicalText || directApiText;

  return {
    ...candidate,
    firstPublicDate: new Date(Date.parse(candidate.firstPublicDate)).toISOString(),
    identityVerified: true,
    identityEvidence: identity.evidence,
    retrievedContent: retrieved.bytes,
    retrievedContentType: retrieved.contentType,
    verifiedText,
  };
}
