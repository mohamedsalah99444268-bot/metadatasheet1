import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ValidationPage from "../pages/ValidationPage";
import { renderWithProviders } from "../test/render";

const spec = {
  id: 42, component_id: 3, part_number: "LM358", manufacturer: "Texas Instruments", document_id: null,
  parameter: "supply_voltage", label: "Supply voltage", category: "electrical", condition_type: "recommended_operating",
  value_text: "3 to 32", unit: "V", min_value: 3, typ_value: null, max_value: 32, test_condition: null, page_number: 4,
  source_text: "VCC 3 V to 32 V", confidence: 0.9, extraction_method: "deterministic", validation_status: "pending",
  reviewer_comment: null, reviewed_at: null,
};

const mocks = vi.hoisted(() => ({
  listSpecs: vi.fn(), acceptSpec: vi.fn(), rejectSpec: vi.fn(), editSpec: vi.fn(), addSpec: vi.fn(), getSpecLog: vi.fn(), getPages: vi.fn(),
}));
vi.mock("../api", () => mocks);
const pdfProps = vi.hoisted(() => ({ calls: [] as { documentId: number; targetPage: number | null }[] }));
vi.mock("../components/PdfViewer", () => ({
  default: (p: { documentId: number; targetPage: number | null }) => { pdfProps.calls.push({ documentId: p.documentId, targetPage: p.targetPage }); return <div data-testid="pdf" data-page={p.targetPage ?? ""} />; },
}));

describe("ValidationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.listSpecs.mockResolvedValue({ items: [spec], total: 1, page: 1, page_size: 25 });
    mocks.acceptSpec.mockResolvedValue({ ...spec, validation_status: "accepted" });
    mocks.rejectSpec.mockResolvedValue({ ...spec, validation_status: "rejected" });
  });

  it("charge les specs en attente et accepte via POST /specs/{id}/accept", async () => {
    renderWithProviders(<ValidationPage />, "/validation");
    expect((await screen.findAllByText("Tension d’alimentation")).length).toBe(2);
    // phone card + desktop row render the same spec; the card carries value, meta and 3 actions
    const card = document.querySelector(".m-cards .m-card")!;
    expect(card.querySelector(".m-value")?.textContent).toBeTruthy();
    fireEvent.click(card.querySelector(".m-more")!);
    expect(document.querySelectorAll(".sheet .sheet-item")).toHaveLength(4);
    expect(mocks.listSpecs.mock.calls[0][0]).toMatchObject({ status: "pending", page: 1 });

    fireEvent.click(screen.getAllByRole("button", { name: "Accepter" })[0]);
    await waitFor(() => expect(mocks.acceptSpec).toHaveBeenCalledWith(42, undefined));
    expect(await screen.findByText("Spécification acceptée.")).toBeInTheDocument();
    expect(screen.getAllByText("Accepté").length).toBeGreaterThan(0);
  });

  it("rejette via l'endpoint reject et affiche l'erreur réelle en cas d'échec", async () => {
    mocks.rejectSpec.mockRejectedValueOnce(new Error("Erreur API 500 : boom"));
    renderWithProviders(<ValidationPage />, "/validation");
    await screen.findAllByText("Tension d’alimentation");
    fireEvent.click(screen.getAllByRole("button", { name: "Rejeter" })[0]);
    await waitFor(() => expect(mocks.rejectSpec).toHaveBeenCalledWith(42, undefined));
    expect(await screen.findByText("Erreur API 500 : boom")).toBeInTheDocument();
    expect(screen.queryByText("Spécification rejetée.")).toBeNull();
  });

  it("ouvre le PDF du tiroir à la page de la spécification", async () => {
    mocks.listSpecs.mockResolvedValue({ items: [{ ...spec, document_id: 9, page_number: 13 }], total: 1, page: 1, page_size: 25 });
    mocks.getSpecLog.mockResolvedValue([]);
    mocks.getPages.mockResolvedValue([]);
    renderWithProviders(<ValidationPage />, "/validation");
    await screen.findAllByText("Tension d’alimentation");
    fireEvent.click(document.querySelector(".validation-table tbody tr")!);
    expect((await screen.findByTestId("pdf")).dataset.page).toBe("13");
    expect(pdfProps.calls[pdfProps.calls.length - 1]).toEqual({ documentId: 9, targetPage: 13 });
  });
});
