import { describe, expect, it } from "vitest";
import { translateEvent } from "../lib/eventMessages";
import raw from "./fixtures/backend-messages.txt?raw";

// Non user-visible strings (class names, prompts, docstrings, headers, part numbers).
const SKIP = [/^AgentEvent$/, /^AnalysisReport$/, /^DatasheetCandidate$/, /^SpecificationEvidence$/, /^ValidationResult$/, /^User-Agent$/, /^SmartDatasheetAI\//, /^STM32/, /^Classify each/, /^Do not add parameters/, /^Category from the title/, /^Evidence \+ range/, /^Index the analysed PDF/, /^One table row/, /^Set category/, /^Wrap a node/];
const SAMPLE: Record<string, string> = { "len(specifications)": "12", "summary": "electrical=8, thermal=4", "len(candidates)": "2", "best.source_domain": "ti.com", "result.get('chunks', 0)": "40", "message": "Indexed 3 chunk(s).", "rejected": "3", "response.status_code": "404", "len(results)": "20", "len(extra)": "2" };

function load(): string[] {
  return raw.split("\n").map((l) => l.trim()).filter(Boolean);
}
function materialise(line: string): string {
  let s = line.replace(/^f?"/, "").replace(/"$/, "");
  s = s.replace(/\{([^}]+)\}/g, (_, k: string) => SAMPLE[k] ?? "x");
  return s.replace(/%s/g, "abc123");
}

describe("backend message translations", () => {
  const lines = load();
  it("fixture is present", () => expect(lines.length).toBeGreaterThan(70));
  for (const line of lines) {
    const msg = materialise(line);
    if (SKIP.some((r) => r.test(msg))) continue;
    it(`translates: ${msg}`, () => {
      expect(translateEvent(msg, "fr")).not.toBe(msg);
      expect(translateEvent(msg, "en")).toBe(msg);
    });
  }
});
