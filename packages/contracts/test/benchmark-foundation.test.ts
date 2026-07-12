import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  assertBenchmarkSourceUniverse,
  assertCustodyState,
  assertMeteringReconciliation,
  assertReplacementLedger,
  assertSterileRootCapability,
  parseExclusiveLedgerAssignment,
} from "../src";

const fixtureRoot = resolve(import.meta.dir, "../../../tests/fixtures/contracts/sample-run");
const fixture = (name: string) => JSON.parse(readFileSync(resolve(fixtureRoot, `${name}.json`), "utf8"));

describe("benchmark provenance, custody, and metering contracts", () => {
  test("enforces the frozen source universe and outcome-blind replacement ledger", () => {
    const universe = fixture("benchmark-source-universe");
    expect(() => assertBenchmarkSourceUniverse(universe)).not.toThrow();
    expect(() => assertReplacementLedger(fixture("benchmark-replacement-ledger"))).not.toThrow();
    expect(() => assertBenchmarkSourceUniverse({ ...universe, cutoff: "2026-01-29T00:00:00Z" })).toThrow(
      /historical cutoff/,
    );
    expect(() => assertBenchmarkSourceUniverse({ ...universe, outcome: "accept" })).toThrow(
      /forbidden field outcome/,
    );
  });

  test("requires reveal prerequisites and terminal quarantine reasons", () => {
    const planned = fixture("benchmark-custody-state");
    expect(() => assertCustodyState(planned)).not.toThrow();
    expect(() => assertCustodyState({ ...planned, state: "reveal_ready" })).toThrow(/prerequisites/);
    expect(() => assertCustodyState({ ...planned, state: "quarantined" })).toThrow(/quarantine/);
  });

  test("requires sterile roots with distinct RPCs and complete denied capabilities", () => {
    const sterile = fixture("benchmark-sterile-root-capability");
    expect(() => assertSterileRootCapability(sterile)).not.toThrow();
    expect(() => assertSterileRootCapability({ ...sterile, network_enabled: true })).toThrow(/network and DNS/);
    expect(() => assertSterileRootCapability({ ...sterile, ever_rpc_socket: sterile.prompt_rpc_socket })).toThrow(
      /distinct authenticated RPCs/,
    );
  });

  test("assigns every usage record exclusively to one paper or arm ledger", () => {
    expect(parseExclusiveLedgerAssignment("paper:arm-v2:v2:S1")).toEqual({
      kind: "paper",
      armId: "arm-v2",
      profileId: "v2",
      paperSlot: "S1",
    });
    expect(parseExclusiveLedgerAssignment("arm:arm-v2:reserve")).toEqual({ kind: "arm", armId: "arm-v2" });
    expect(() => parseExclusiveLedgerAssignment("paper:arm-v2:S1")).toThrow(/exactly one/);
    const reconciliation = fixture("benchmark-metering-reconciliation");
    expect(() => assertMeteringReconciliation(reconciliation)).not.toThrow();
    expect(() => assertMeteringReconciliation({ ...reconciliation, cap_status: "over_cap" })).toThrow(/over cap/);
  });
});
