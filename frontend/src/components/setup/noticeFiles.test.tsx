import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BudgetLine, FtRecord } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { sampleRecord, SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { NoticeFilesProvider, noticeFilesFor, noticeFilesFrom, type NoticeFiles } from "./noticeFiles";
import { TypeTermForm } from "./TypeTermForm";

describe("the grant's notice files", () => {
  it("are the files its terms were read from, in the order they arrived", async () => {
    const api = createFakeApiClient();
    const [detail, cards] = await Promise.all([api.getGrant(SAMPLE_GRANT_ID), api.listEvidence(SAMPLE_GRANT_ID)]);
    expect(noticeFilesFrom(detail.terms, cards)).toEqual([
      { id: "file-award-letter", name: "award_letter.txt" },
      { id: "file-extension-notice", name: "extension_notice.txt" },
    ]);
  });
});

describe("noticeFilesFor", () => {
  it("doesn't offer a file whose only term was rejected", async () => {
    const api = createFakeApiClient();
    const [detail, cards] = await Promise.all([api.getGrant(SAMPLE_GRANT_ID), api.listEvidence(SAMPLE_GRANT_ID)]);
    const terms = detail.terms.map((t) => (t.record.id === "rec-period-extension" ? { ...t, state: "rejected" as const } : t));
    expect(noticeFilesFor(terms, { data: cards }).files.map((f) => f.id)).toEqual(["file-award-letter"]);
    expect(noticeFilesFor(terms, {}).status).toBe("loading");
    expect(noticeFilesFor(terms, { error: new Error("x") }).status).toBe("error");
  });
});

describe("typing a budget line", () => {
  const files = [
    { id: "file-award-letter", name: "award_letter.txt" },
    { id: "file-extension-notice", name: "extension_notice.txt" },
  ];
  const line = sampleRecord<FtRecord<BudgetLine>>("rec-budget-other");
  const ready = (offered: { id: string; name: string }[], names: Record<string, string> = {}): NoticeFiles => ({
    status: "ready",
    files: offered,
    names: { ...Object.fromEntries(offered.map((f) => [f.id, f.name])), ...names },
  });
  const form = (notices: NoticeFiles, term: FtRecord<BudgetLine> = line, onSave = vi.fn()) =>
    render(
      <NoticeFilesProvider value={notices}>
        <TypeTermForm term={term} kind="budget_line" saving={false} onSave={onSave} onCancel={() => {}} />
      </NoticeFilesProvider>,
    );

  it("says the notices are loading, or couldn't load, rather than that none is on file", () => {
    const { unmount } = form({ status: "loading", files: [], names: {} });
    expect(screen.getByText("Loading the grant's notices…")).toBeInTheDocument();
    expect(screen.queryByText("No notice is on file for this grant yet.")).toBeNull();
    unmount();
    form({ status: "error", files: [], names: {} });
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load the grant's notices.");
    expect(screen.queryByText("No notice is on file for this grant yet.")).toBeNull();
  });

  it("shows a saved notice that's no longer offered by its file's name, or says it's no longer offered", () => {
    const saved = { ...line, data: { ...line.data, notice_file_id: "file-old-amendment" } };
    const { unmount } = form(ready(files, { "file-old-amendment": "amendment_001.pdf" }), saved);
    const notice = screen.getByLabelText("Notice") as HTMLSelectElement;
    expect(notice.value).toBe("file-old-amendment");
    expect(notice.selectedOptions[0].textContent).toBe("amendment_001.pdf");
    unmount();
    form(ready(files), saved);
    expect((screen.getByLabelText("Notice") as HTMLSelectElement).selectedOptions[0].textContent).toBe("A file no longer offered");
  });

  it("asks which notice the line belongs to, starting from the file it was read from", () => {
    const onSave = vi.fn();
    render(
      <NoticeFilesProvider value={ready(files)}>
        <TypeTermForm term={line} kind="budget_line" saving={false} onSave={onSave} onCancel={() => {}} />
      </NoticeFilesProvider>,
    );
    const notice = screen.getByLabelText("Notice") as HTMLSelectElement;
    expect(notice.value).toBe("file-award-letter");
    fireEvent.change(notice, { target: { value: "file-extension-notice" } });
    fireEvent.click(screen.getByRole("button", { name: "Save typed value" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ kind: "budget_line", notice_file_id: "file-extension-notice" }));
  });

  it("won't save without a notice", () => {
    const onSave = vi.fn();
    render(
      <NoticeFilesProvider value={ready([])}>
        <TypeTermForm term={line} kind="budget_line" saving={false} onSave={onSave} onCancel={() => {}} />
      </NoticeFilesProvider>,
    );
    expect(screen.getByText("No notice is on file for this grant yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save typed value" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Notice is needed.");
  });
});
