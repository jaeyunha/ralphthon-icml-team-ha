import { ViewerDataNotFoundError, ViewerFixtureError } from "./viewer-data";

export type RouteParams<T extends Record<string, string>> = {
  params: T | Promise<T>;
};

export class ViewerApiRequestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ViewerApiRequestError";
  }
}

export function jsonResponse(value: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("cache-control", "no-store");
  return new Response(JSON.stringify(value), { ...init, headers });
}

export async function apiResponse(action: () => Promise<unknown>): Promise<Response> {
  try {
    return jsonResponse(await action());
  } catch (error) {
    if (error instanceof ViewerApiRequestError) {
      return jsonResponse({ error: "bad_request", message: error.message }, { status: 400 });
    }
    if (error instanceof ViewerDataNotFoundError) {
      return jsonResponse({ error: "not_found", message: error.message }, { status: 404 });
    }
    if (error instanceof ViewerFixtureError) {
      return jsonResponse(
        { error: "fixture_unavailable", message: "The viewer fixture could not be loaded." },
        { status: 500 },
      );
    }
    return jsonResponse({ error: "internal_error", message: "The request could not be completed." }, { status: 500 });
  }
}

export function parseNonNegativeSequence(value: string | null, field: string): number {
  if (value === null || value === "") return 0;
  if (!/^\d+$/.test(value)) throw new ViewerApiRequestError(`${field} must be a non-negative integer`);
  const sequence = Number(value);
  if (!Number.isSafeInteger(sequence)) throw new ViewerApiRequestError(`${field} is outside the supported range`);
  return sequence;
}
