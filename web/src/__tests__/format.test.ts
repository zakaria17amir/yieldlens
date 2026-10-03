import { describe, expect, it } from "vitest";
import { formatBps, formatUsdg, shortAddr, splitLabel } from "../format";

describe("format", () => {
  it("formats basis points as percent", () => {
    expect(formatBps(1840)).toBe("18.40%");
    expect(formatBps(0)).toBe("0.00%");
    expect(formatBps(10000)).toBe("100.00%");
    expect(formatBps(5)).toBe("0.05%");
  });

  it("formats 6-decimal USDG with separators and 2 dp", () => {
    expect(formatUsdg(0n)).toBe("0.00");
    expect(formatUsdg(1_234_567_890n)).toBe("1,234.56");
    expect(formatUsdg(1_000_000_000_000n)).toBe("1,000,000.00");
    expect(formatUsdg(999_999n)).toBe("0.99");
    expect(formatUsdg(100_000_000n)).toBe("100.00");
  });

  it("labels a fixed/floating split", () => {
    expect(splitLabel(3000)).toBe("30% fixed / 70% floating");
    expect(splitLabel(0)).toBe("0% fixed / 100% floating");
    expect(splitLabel(10000)).toBe("100% fixed / 0% floating");
    expect(splitLabel(3333)).toBe("33.33% fixed / 66.67% floating");
  });

  it("shortens addresses", () => {
    expect(shortAddr("0x1234567890abcdef1234567890abcdef12345678")).toBe("0x1234…5678");
  });
});
