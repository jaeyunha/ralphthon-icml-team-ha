import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { canonicalJson } from "./canonical-json";

export type Sha256 = `sha256:${string}`;

export function sha256Bytes(value: string | Uint8Array): Sha256 {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

export function sha256CanonicalJson(value: unknown): Sha256 {
  return sha256Bytes(canonicalJson(value));
}

export async function sha256File(path: string): Promise<Sha256> {
  return sha256Bytes(await readFile(path));
}

export function isSha256(value: string): value is Sha256 {
  return /^sha256:[0-9a-f]{64}$/.test(value);
}
