import type { ReactNode } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Providers } from "../App";

export function renderWithProviders(ui: ReactNode, route = "/") {
  return render(<MemoryRouter initialEntries={[route]}><Providers>{ui}</Providers></MemoryRouter>);
}
