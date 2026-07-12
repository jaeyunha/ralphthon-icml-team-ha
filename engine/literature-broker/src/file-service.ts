import { atomicWriteJson } from "../../../packages/contracts/src/atomic-write";
import { mkdir, readFile, readdir, rename } from "node:fs/promises";
import { basename, dirname, join, resolve, sep } from "node:path";
import type { LiteratureBroker } from "./broker";
import type { BrokerRefusal, BrokerResult } from "./types";

const SAFE_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export interface ReviewerMailbox {
  runId: string;
  reviewerId: string;
  reviewerWorkspace: string;
}

function safeIdentifier(value: string, label: string): string {
  if (!SAFE_IDENTIFIER.test(value)) throw new Error(`${label} is not filesystem-safe`);
  return value;
}

function confined(root: string, ...parts: string[]): string {
  const resolvedRoot = resolve(root);
  const path = resolve(resolvedRoot, ...parts);
  if (path !== resolvedRoot && !path.startsWith(`${resolvedRoot}${sep}`)) {
    throw new Error("mailbox path escapes reviewer workspace");
  }
  return path;
}

async function atomicJsonWrite(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  await atomicWriteJson(path, value, () => true, {
    createParent: false,
    mode: 0o600,
    replaceExisting: true,
  });
}

function fallbackRequestId(path: string): string {
  const stem = basename(path).replace(/\.json$/u, "");
  return SAFE_IDENTIFIER.test(stem) ? stem : "unknown-request";
}

function refusal(
  requestId: string,
  reviewerId: string,
  message: string,
  now: () => Date,
  stage: BrokerRefusal["stage"] = "request_validation",
): BrokerRefusal {
  return {
    artifact_type: "literature_broker_refusal",
    request_id: requestId,
    reviewer_id: reviewerId,
    code: stage === "internal" ? "INTERNAL_ERROR" : "INVALID_REQUEST",
    stage,
    message,
    retryable: stage === "internal",
    created_at: now().toISOString(),
  };
}

export class BrokerFileService {
  constructor(
    private readonly broker: LiteratureBroker,
    private readonly now: () => Date = () => new Date(),
  ) {}

  async processFile(mailbox: ReviewerMailbox, requestPath: string): Promise<BrokerResult> {
    const runId = safeIdentifier(mailbox.runId, "run ID");
    const reviewerId = safeIdentifier(mailbox.reviewerId, "reviewer ID");
    const outbox = confined(mailbox.reviewerWorkspace, "outbox", "literature");
    const absoluteRequestPath = resolve(requestPath);
    if (!absoluteRequestPath.startsWith(`${outbox}${sep}`) || !absoluteRequestPath.endsWith(".json")) {
      throw new Error("request file is outside the reviewer literature outbox");
    }

    let value: unknown;
    let result: BrokerResult;
    try {
      value = JSON.parse(await readFile(absoluteRequestPath, "utf8"));
      const item = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
      if (item.runId !== runId || item.reviewerId !== reviewerId) {
        result = refusal(
          typeof item.requestId === "string" ? item.requestId : fallbackRequestId(absoluteRequestPath),
          reviewerId,
          "Request run/reviewer binding does not match its private mailbox.",
          this.now,
        );
      } else {
        result = await this.broker.process(value);
      }
    } catch (error) {
      result = refusal(
        fallbackRequestId(absoluteRequestPath),
        reviewerId,
        error instanceof SyntaxError
          ? "Request file is not valid JSON."
          : `Broker failed safely: ${error instanceof Error ? error.message : String(error)}`,
        this.now,
        error instanceof SyntaxError ? "request_validation" : "internal",
      );
    }

    const inbox = confined(mailbox.reviewerWorkspace, "inbox", "literature");
    const archive = confined(mailbox.reviewerWorkspace, "processed", "literature");
    const responsePath = join(inbox, `${safeIdentifier(result.request_id, "request ID")}.json`);
    await atomicJsonWrite(responsePath, result);
    await mkdir(archive, { recursive: true, mode: 0o700 });
    await rename(absoluteRequestPath, join(archive, basename(absoluteRequestPath)));
    return result;
  }

  async processPending(mailbox: ReviewerMailbox): Promise<BrokerResult[]> {
    const outbox = confined(mailbox.reviewerWorkspace, "outbox", "literature");
    await mkdir(outbox, { recursive: true, mode: 0o700 });
    const files = (await readdir(outbox, { withFileTypes: true }))
      .filter((entry) => entry.isFile() && entry.name.endsWith(".json") && !entry.name.includes(".tmp-"))
      .map((entry) => join(outbox, entry.name))
      .sort();
    const results: BrokerResult[] = [];
    for (const path of files) results.push(await this.processFile(mailbox, path));
    return results;
  }
}
