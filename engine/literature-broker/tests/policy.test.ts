import { describe, expect, test } from "bun:test";
import { evaluateCandidateAdmissibility, isOnOrBeforeCutoff } from "../src/cutoff";
import { buildTargetFingerprint, matchTargetFingerprint } from "../src/fingerprint";
import { evaluateQueryPolicy } from "../src/policy";
import type { DiscoveryCandidate, FrozenPaper, QueryRequest, RefusalCode } from "../src/types";

const fixtureRoot = new URL("../../../tests/fixtures/broker/", import.meta.url);
const frozenPaper = (await Bun.file(new URL("34584/frozen-paper.json", fixtureRoot)).json()) as FrozenPaper;
const fingerprint = buildTargetFingerprint(frozenPaper);
const policyCases = (await Bun.file(new URL("policy-queries.json", fixtureRoot)).json()) as Array<{
  name: string;
  query: string;
  code: RefusalCode;
}>;

function request(query: string): QueryRequest {
  return {
    requestId: "REQ-policy-1",
    runId: "run-historical",
    reviewerId: "reviewer-r2",
    query,
    queryKind: "conceptual_prior_work",
    retrievalReason: "Check conceptual predecessors for claim C1",
    mode: "historical_benchmark",
    literatureCutoff: "2026-01-28T23:59:59-12:00",
    targetFingerprint: fingerprint,
    maxResults: 5,
    createdAt: "2026-01-28T12:00:00Z",
  };
}

function candidate(overrides: Partial<DiscoveryCandidate> = {}): DiscoveryCandidate {
  return {
    backend: "fixture",
    sourceType: "arxiv_preprint",
    canonicalUri: "https://arxiv.org/abs/2105.04026",
    title: "Group Actions in Neural Approximation",
    authors: ["Alice Example"],
    firstPublicDate: "2021-05-10T18:00:00Z",
    ...overrides,
  };
}

describe("query policy", () => {
  const cases = policyCases;

  for (const fixture of cases) {
    test(`rejects ${fixture.name}`, () => {
      const decision = evaluateQueryPolicy(request(fixture.query), () => new Date("2026-01-28T12:00:00Z"));
      expect(decision.allowed).toBeFalse();
      if (!decision.allowed) {
        expect(decision.refusal.code).toBe(fixture.code);
        expect(decision.refusal.artifact_type).toBe("literature_broker_refusal");
        expect(decision.refusal.request_id).toBe("REQ-policy-1");
      }
    });
  }

  test("allows a conceptual prior-work query", () => {
    expect(evaluateQueryPolicy(request("categorical symmetry methods for neural architectures"))).toEqual({ allowed: true });
  });
});

describe("34584 target fingerprint", () => {
  test("contains title n-grams without storing raw case", () => {
    expect(fingerprint.normalizedTitle).toBe(
      "foundations of equivariant deep learning unifying graph and sheaf neural networks",
    );
    expect(fingerprint.titleNgrams).toContain("unifying graph and sheaf");
  });

  test("blocks title, author, sentence, and canonical identifier probes", () => {
    expect(matchTargetFingerprint(frozenPaper.title, fingerprint)?.kind).toBe("title");
    expect(matchTargetFingerprint("recent work by Maruyama", fingerprint)?.kind).toBe("author");
    expect(matchTargetFingerprint(frozenPaper.distinctiveSentences?.[0] ?? "", fingerprint)?.kind).toBe(
      "distinctive_sentence",
    );
    expect(matchTargetFingerprint("forum aIH1jyU37z", fingerprint)?.kind).toBe("canonical_uri");
  });
});

describe("cutoff and target duplicate filter", () => {
  test("treats the historical cutoff boundary as inclusive", () => {
    expect(isOnOrBeforeCutoff("2026-01-29T11:59:59Z", "2026-01-28T23:59:59-12:00")).toBeTrue();
    expect(
      evaluateCandidateAdmissibility(
        candidate({ firstPublicDate: "2026-01-29T11:59:59Z" }),
        request("categorical symmetry methods"),
      ),
    ).toMatchObject({ allowed: true });
  });

  test("rejects a source one second after the historical cutoff", () => {
    expect(
      evaluateCandidateAdmissibility(
        candidate({ firstPublicDate: "2026-01-29T12:00:00Z" }),
        request("categorical symmetry methods"),
      ),
    ).toEqual({ allowed: false, reason: "post_cutoff" });
  });

  test("rejects missing dates and target duplicates", () => {
    const missingDate = candidate();
    delete missingDate.firstPublicDate;
    expect(evaluateCandidateAdmissibility(missingDate, request("categorical symmetry methods"))).toEqual({
      allowed: false,
      reason: "missing_first_public_date",
    });
    expect(
      evaluateCandidateAdmissibility(
        candidate({ title: frozenPaper.title, canonicalUri: "https://example.org/target-copy" }),
        request("categorical symmetry methods"),
      ),
    ).toEqual({ allowed: false, reason: "target_duplicate" });
  });
});
