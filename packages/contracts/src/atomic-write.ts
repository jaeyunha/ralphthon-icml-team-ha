import { randomUUID } from "node:crypto";
import { chmod, link, mkdir, open, rename, rm } from "node:fs/promises";
import { basename, dirname, join } from "node:path";

export interface AtomicValidationContext {
  readonly temporaryPath: string;
  readonly bytes: Uint8Array;
}

export type AtomicValidator<T> = (
  value: T,
  context: AtomicValidationContext,
) => boolean | void | Promise<boolean | void>;

export interface AtomicWriteOptions {
  readonly mode?: number;
  readonly createParent?: boolean;
  readonly replaceExisting?: boolean;
}

export class AtomicWriteValidationError extends Error {
  readonly targetPath: string;

  constructor(targetPath: string) {
    super(`Validation rejected atomic write to ${targetPath}`);
    this.name = "AtomicWriteValidationError";
    this.targetPath = targetPath;
  }
}

export async function atomicWriteJson<T>(
  targetPath: string,
  value: T,
  validate: AtomicValidator<T>,
  options: AtomicWriteOptions = {},
): Promise<void> {
  const bytes = new TextEncoder().encode(`${JSON.stringify(value, null, 2)}\n`);
  await atomicWriteBytes(targetPath, bytes, async (context) => validate(value, context), options);
}

export async function atomicPublishJson<T>(
  targetPath: string,
  value: T,
  validate: AtomicValidator<T>,
  options: AtomicWriteOptions = {},
): Promise<void> {
  await atomicWriteJson(targetPath, value, validate, { ...options, replaceExisting: false });
}

export async function atomicWriteBytes(
  targetPath: string,
  bytes: Uint8Array,
  validate: (context: AtomicValidationContext) => boolean | void | Promise<boolean | void>,
  options: AtomicWriteOptions = {},
): Promise<void> {
  const parent = dirname(targetPath);
  if (options.createParent ?? true) {
    await mkdir(parent, { recursive: true });
  }

  const temporaryPath = join(parent, `.${basename(targetPath)}.tmp-${process.pid}-${randomUUID()}`);
  let temporaryExists = false;
  try {
    const handle = await open(temporaryPath, "wx", options.mode ?? 0o600);
    temporaryExists = true;
    try {
      await handle.writeFile(bytes);
      await handle.sync();
    } finally {
      await handle.close();
    }

    const accepted = await validate({ temporaryPath, bytes });
    if (accepted === false) {
      throw new AtomicWriteValidationError(targetPath);
    }

    if (options.mode !== undefined) {
      await chmod(temporaryPath, options.mode);
    }
    if (options.replaceExisting ?? true) {
      await rename(temporaryPath, targetPath);
    } else {
      await link(temporaryPath, targetPath);
      await rm(temporaryPath);
    }
    temporaryExists = false;
    await syncDirectory(parent);
  } finally {
    if (temporaryExists) {
      await rm(temporaryPath, { force: true });
    }
  }
}

async function syncDirectory(path: string): Promise<void> {
  const handle = await open(path, "r");
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}
