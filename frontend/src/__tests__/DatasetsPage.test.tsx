import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DatasetsPage from "../pages/DatasetsPage";
import { renderWithProviders } from "../test/render";

const mocks = vi.hoisted(() => ({
  listAnalysisDatasets: vi.fn(), getDatasetProfile: vi.fn(), getDatasetPreview: vi.fn(), uploadAnalysisDataset: vi.fn(),
  cleanDataset: vi.fn(), deleteAnalysisDataset: vi.fn(), downloadFile: vi.fn(),
  DOWNLOAD_PATHS: { datasetExport: (id: number, f: string) => `/datasets/${id}/export?format=${f}` },
}));
vi.mock("../api", () => mocks);

describe("DatasetsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.listAnalysisDatasets.mockResolvedValue([{ id: 5, filename: "mesures.csv", rows: 120, columns: 2, created_at: "2026-11-18T10:00:00Z" }]);
    mocks.getDatasetProfile.mockResolvedValue({
      columns: [
        { name: "tension_v", dtype: "numeric", missing: 3, missing_pct: 2.5, unique: 80, outliers: 2,
          stats: { mean: 3.3, std: 0.1, min: 3, q1: 3.2, median: 3.3, q3: 3.4, max: 3.6 },
          histogram: [{ bin_start: 3, bin_end: 3.3, count: 60 }, { bin_start: 3.3, bin_end: 3.6, count: 57 }] },
        { name: "fabricant", dtype: "categorical", missing: 0, missing_pct: 0, unique: 4, outliers: 0, top_values: [{ value: "TI", count: 70 }] },
      ],
      duplicates: 1,
      correlation: { columns: ["tension_v"], matrix: [[1]] },
      suggestions: [{ column: "tension_v", kind: "missing", message: "3 valeurs manquantes : imputer par la médiane" }],
    });
  });

  it("affiche le profil réel : colonnes, types, suggestions", async () => {
    renderWithProviders(<DatasetsPage />, "/datasets");
    expect(await screen.findByText("3 valeurs manquantes : imputer par la médiane")).toBeInTheDocument();
    expect(mocks.getDatasetProfile).toHaveBeenCalledWith(5, expect.anything());
    expect(screen.getAllByText("tension_v").length).toBeGreaterThan(0);
    expect(screen.getByText("Numérique")).toBeInTheDocument();
    expect(screen.getByText("Catégorielle")).toBeInTheDocument();
    expect(screen.getByText("TI")).toBeInTheDocument();
    expect(screen.getByText("Il faut au moins deux colonnes numériques.")).toBeInTheDocument();
  });
});
