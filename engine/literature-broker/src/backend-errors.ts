export class BackendError extends Error {
  constructor(
    readonly backend: "ever" | "arxiv" | "crossref",
    message: string,
    readonly retryable = true,
  ) {
    super(message);
    this.name = "BackendError";
  }
}

export function timeoutSignal(timeoutMs: number): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return { signal: controller.signal, clear: () => clearTimeout(timer) };
}
