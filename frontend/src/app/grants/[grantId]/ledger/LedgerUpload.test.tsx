import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient, type LedgerUploadResult } from "@/lib/api";
import { StaticAuthProvider, type Auth } from "@/lib/auth";
import { LedgerUpload } from "./LedgerUpload";

const auth: Auth = {
  state: { status: "signed_in", user: { id: "user-1", email: "accountant@university.example", name: null } },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

function setup(answer: LedgerUploadResult) {
  const uploadLedger = vi.fn(async () => answer);
  render(
    <StaticAuthProvider value={auth}>
      <ApiProvider client={{ uploadLedger } as unknown as ApiClient}>
        <LedgerUpload grantId="g-1" />
      </ApiProvider>
    </StaticAuthProvider>,
  );
  return uploadLedger;
}

describe("LedgerUpload", () => {
  it("sends the file and shows each rejected row with its number and reason", async () => {
    const upload = setup({
      added: 2,
      already_present: 1,
      rejected: [
        { row: 4, message: "posting_date isn't a date: 2026-13-01" },
        { row: 7, message: "The row has no line_id." },
      ],
    });
    const file = new File(["line_id,amount\n"], "ledger.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("Ledger file"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(upload).toHaveBeenCalledWith("g-1", file, "ledger.csv"));
    const result = await screen.findByRole("status");
    expect(result).toHaveTextContent("2 lines added");
    expect(result).toHaveTextContent("1 line already on file, skipped");
    expect(result).toHaveTextContent("2 rows rejected");
    const rows = within(result).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent)).toEqual([
      "4posting_date isn't a date: 2026-13-01",
      "7The row has no line_id.",
    ]);
  });

  it("has nothing to send until a file is chosen", () => {
    setup({ added: 0, already_present: 0, rejected: [] });
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  });
});
