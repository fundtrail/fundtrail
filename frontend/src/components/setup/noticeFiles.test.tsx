import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BudgetLine, FtRecord } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { sampleRecord, SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { NoticeFilesProvider, noticeFilesFrom } from "./noticeFiles";
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

describe("typing a budget line", () => {
  const files = [
    { id: "file-award-letter", name: "award_letter.txt" },
    { id: "file-extension-notice", name: "extension_notice.txt" },
  ];
  const line = sampleRecord<FtRecord<BudgetLine>>("rec-budget-other");

  it("asks which notice the line belongs to, starting from the file it was read from", () => {
    const onSave = vi.fn();
    render(
      <NoticeFilesProvider files={files}>
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
      <NoticeFilesProvider files={[]}>
        <TypeTermForm term={line} kind="budget_line" saving={false} onSave={onSave} onCancel={() => {}} />
      </NoticeFilesProvider>,
    );
    expect(screen.getByText("No notice is on file for this grant yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save typed value" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Notice is needed.");
  });
});
