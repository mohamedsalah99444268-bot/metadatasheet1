import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppProvider } from "../state/AppContext";
import WorkspacePage from "../pages/WorkspacePage";

const { documentMeta, parsedField } = vi.hoisted(() => ({
  documentMeta: {
    id: 7,
    original_filename: "STM32F103.pdf",
    sha256: "abc",
    uploaded_at: "2026-01-01T00:00:00Z",
    page_count: 2,
  },
  parsedField: {
    id: 101,
    document_id: 7,
    field_type: "part_number",
    value: "STM32F103",
    confidence: 0.94,
    parser_rule: "table",
    section_name: null,
    page_number: 1,
    source_text: "STM32F103",
    x0: 0,
    y0: 0,
    x1: 10,
    y1: 10,
    variant_group: "g1",
  },
}));

vi.mock("../api", () => ({
  getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
  getAiHealth: vi.fn().mockResolvedValue({
    status: "unavailable",
    runtime: "ollama",
    base_url: "http://localhost:11434",
    model: "",
    model_installed: false,
    message: "",
  }),
  listImportJobs: vi.fn().mockResolvedValue([]),
  listDocuments: vi.fn().mockResolvedValue([documentMeta]),
  getParsedFields: vi.fn().mockResolvedValue([parsedField]),
  getPages: vi.fn().mockResolvedValue([]),
  getTextBlocks: vi.fn().mockResolvedValue([]),
  getTables: vi.fn().mockResolvedValue([]),
  getImportJob: vi.fn(),
  uploadDocument: vi.fn(),
}));

vi.mock("../components/DocumentViewer", () => ({
  default: () => null,
}));

describe("WorkspacePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("affiche la Sidebar existante à côté de la visionneuse", async () => {
    render(
      <MemoryRouter initialEntries={["/workspace/7"]}>
        <AppProvider>
          <WorkspacePage />
        </AppProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Données extraites")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Résumé" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "STM32F103.pdf" })).toBeInTheDocument();
  });
});
