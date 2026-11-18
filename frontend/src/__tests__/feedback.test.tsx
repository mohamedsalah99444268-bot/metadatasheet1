import { useState } from "react";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useConfirm } from "../components/feedback";
import { useI18n } from "../lib/i18n";
import { renderWithProviders } from "../test/render";

function DeleteButton() {
  const confirm = useConfirm();
  const [result, setResult] = useState("idle");
  return (
    <>
      <button onClick={async () => setResult((await confirm({ title: "Supprimer ?", message: "Action définitive", confirmLabel: "Oui, supprimer", danger: true })) ? "yes" : "no")}>Supprimer</button>
      <span data-testid="result">{result}</span>
    </>
  );
}

function LangToggle() {
  const { t, lang, setLang } = useI18n();
  return <button onClick={() => setLang(lang === "fr" ? "en" : "fr")}>{t("nav.dashboard")}</button>;
}

describe("ConfirmDialog", () => {
  it("résout false sur Annuler et true sur confirmation", async () => {
    renderWithProviders(<DeleteButton />);
    fireEvent.click(screen.getByText("Supprimer"));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Action définitive");
    fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.getByTestId("result")).toHaveTextContent("no"));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByText("Supprimer"));
    fireEvent.click(await screen.findByRole("button", { name: "Oui, supprimer" }));
    await waitFor(() => expect(screen.getByTestId("result")).toHaveTextContent("yes"));
  });
});

describe("i18n", () => {
  beforeEach(() => localStorage.clear());

  it("démarre en français, bascule en anglais et persiste le choix", () => {
    renderWithProviders(<LangToggle />);
    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("Tableau de bord");
    fireEvent.click(button);
    expect(button).toHaveTextContent("Dashboard");
    expect(localStorage.getItem("sd_lang")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
  });
});
