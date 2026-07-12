export const RUN_STATES = [
  "CREATED",
  "INGESTING",
  "DOSSIER",
  "PERSONA_ASSIGNMENT",
  "PRELIMINARY_REVIEW",
  "VALIDATION",
  "OFFICIAL_REVIEW",
  "AUTHOR_REBUTTAL",
  "REVIEWER_FOLLOWUP",
  "AUTHOR_FINAL",
  "INTERNAL_DISCUSSION",
  "AC_META_REVIEW",
  "SAC_CALIBRATION",
  "PC_FINALIZATION",
  "COMPLETE",
] as const;

export const RUN_FAILURE_STATES = [
  "INPUT_INVALID",
  "POLICY_BLOCKED",
  "AGENT_FAILED",
  "VALIDATION_FAILED",
  "STALLED",
  "TIME_EXHAUSTED",
  "BUDGET_EXHAUSTED",
  "INCOMPLETE",
] as const;

export type RunActiveState = (typeof RUN_STATES)[number];
export type RunFailureState = (typeof RUN_FAILURE_STATES)[number];
export type RunState = RunActiveState | RunFailureState;

const activeIndex = new Map<RunActiveState, number>(RUN_STATES.map((state, index) => [state, index]));
const failures = new Set<RunState>(RUN_FAILURE_STATES);

export class InvalidRunTransitionError extends Error {
  constructor(from: RunState, to: RunState) {
    super(`Run state cannot transition from ${from} to ${to}`);
    this.name = "InvalidRunTransitionError";
  }
}

export function isTerminalRunState(state: RunState): boolean {
  return state === "COMPLETE" || failures.has(state);
}

export function canTransitionRunState(from: RunState, to: RunState): boolean {
  if (isTerminalRunState(from) || from === to) {
    return false;
  }
  if (failures.has(to)) {
    return true;
  }

  const fromIndex = activeIndex.get(from as RunActiveState);
  const toIndex = activeIndex.get(to as RunActiveState);
  return fromIndex !== undefined && toIndex === fromIndex + 1;
}

export function assertRunTransition(from: RunState, to: RunState): void {
  if (!canTransitionRunState(from, to)) {
    throw new InvalidRunTransitionError(from, to);
  }
}

export class RunStateMachine {
  #state: RunState;

  constructor(initialState: RunState = "CREATED") {
    this.#state = initialState;
  }

  get state(): RunState {
    return this.#state;
  }

  transition(to: RunState): RunState {
    assertRunTransition(this.#state, to);
    this.#state = to;
    return this.#state;
  }
}
