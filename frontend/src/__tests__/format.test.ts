import { describe, expect, it } from "vitest";
import { fmtRange, fmtSI, pickDescription } from "../lib/format";
import { tEnum } from "../lib/enums";
import { translate } from "../lib/i18n";

const nbsp = (s: string) => s.replace(/ | /g, " ");

describe("fmtSI", () => {
  it("applies SI prefixes to base units", () => {
    expect(nbsp(fmtSI(0.0000005, "A", "fr-FR"))).toBe("0,5 µA");
    expect(nbsp(fmtSI(1e-10, "F", "en-US"))).toBe("100 pF");
    expect(nbsp(fmtSI(16000000, "Hz", "en-US"))).toBe("16 MHz");
    expect(nbsp(fmtSI(0.0028, "A", "en-US"))).toBe("2.8 mA");
  });
  it("leaves non-SI units and zero untouched", () => {
    expect(nbsp(fmtSI(95, "dB", "en-US"))).toBe("95 dB");
    expect(nbsp(fmtSI(0, "V", "en-US"))).toBe("0 V");
    expect(fmtSI(null, "V", "en-US")).toBe("—");
  });
});

describe("fmtRange", () => {
  it("joins min / typ / max with prefixed units", () => {
    expect(nbsp(fmtRange({ min_value: 0.000001, typ_value: null, max_value: 0.0005, value_text: null, unit: "A" }, "en-US"))).toBe("min 1 µA · max 0.5 mA");
  });
  it("falls back to the raw text", () => {
    expect(fmtRange({ min_value: null, typ_value: null, max_value: null, value_text: "SOIC-8", unit: null }, "en-US")).toBe("SOIC-8");
  });
});

describe("pickDescription", () => {
  it("skips datasheet revision lines", () => {
    const raw = "SNOSC25D –MAY 1998–REVISED OCTOBER 2015. The LM741 series are general purpose operational amplifiers. More.";
    expect(pickDescription(null, raw)).toBe("The LM741 series are general purpose operational amplifiers.");
  });
  it("returns null when nothing human is left", () => {
    expect(pickDescription("Rev. 3 – 2015", "")).toBeNull();
  });
});

describe("tEnum", () => {
  const t = (k: Parameters<typeof translate>[1]) => translate("fr", k);
  it("translates agents and categories, humanizes unknown values", () => {
    expect(tEnum(t, "agent", "conflict_review")).toBe("Revue des conflits");
    expect(tEnum(t, "cat", "op_amp")).toBe("Ampli-op");
    expect(tEnum(t, "agent", "brand_new_agent")).toBe("Brand new agent");
  });
});

import { parseTs } from "../lib/format";
describe("parseTs", () => {
  it("treats naive backend timestamps as UTC", () => {
    expect(parseTs("2026-11-18T20:54:03.044392").toISOString()).toBe("2026-11-18T20:54:03.044Z");
    expect(parseTs("2026-11-18 20:54:03").toISOString()).toBe("2026-11-18T20:54:03.000Z");
    expect(parseTs("2026-11-18T20:54:03+01:00").toISOString()).toBe("2026-11-18T19:54:03.000Z");
  });
});
