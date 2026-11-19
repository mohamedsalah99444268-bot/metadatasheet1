import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { labelTables } from "../lib/tableLabels";

describe("mobile stacked table cards", () => {
  it("labels every body cell with its column header so the value column is never hidden", () => {
    const { container } = render(
      <table className="table">
        <thead><tr><th>Paramètre</th><th data-label="LM741">LM741<span>Texas Instruments</span></th><th aria-label="Actions" /></tr></thead>
        <tbody><tr><td>Tension</td><td>15 V</td><td><button type="button">Accepter</button></td></tr></tbody>
      </table>,
    );
    labelTables(container);
    const cells = container.querySelectorAll("tbody td");
    expect(cells[0].getAttribute("data-label")).toBe("Paramètre");
    expect(cells[1].getAttribute("data-label")).toBe("LM741");
    expect(cells[1].textContent).toBe("15 V");
    expect(cells[2].getAttribute("data-label")).toBe("Actions");
  });
});
