import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type AnswerView, type ChargeStatus, type ChecklistEntry, type FtRecord, type NewRecordInput, type OpenQuestion, type Reason } from "@/lib/api";
import { parseDollars } from "./actions";
import { AgentAnswers } from "./AgentAnswers";
import { EvidenceChecklist } from "./EvidenceChecklist";
import { StatusReasons } from "./StatusReasons";

function record(id: string, author: "agent" | "user", data: Record<string, unknown>): FtRecord {
  return {
    id,
    workspace_id: "ws",
    grant_id: "g",
    author,
    author_user_id: author === "user" ? "u" : null,
    written_at: "2026-03-01T10:00:00Z",
    replaces_id: null,
    data: data as unknown as FtRecord["data"],
  } as FtRecord;
}

function reason(over: Partial<Reason>): Reason {
  return { check: "checklist", problem: "missing_item", text: "A bill isn't on file.", record_ids: ["r-item"], bucket: "missing_evidence", ...over } as Reason;
}

function status(reasons: Reason[]): ChargeStatus {
  return { grant_id: "g", charge_id: "c", bucket: "possible_conflict", reasons, checklist: [], flagged: true } as ChargeStatus;
}

const writer = () => vi.fn<(input: NewRecordInput) => Promise<void>>(async () => {});

describe("parseDollars", () => {
  it("reads dollars as cents without floating point", () => {
    expect(parseDollars("1,800.00")).toBe(180_000);
    expect(parseDollars("$2,300")).toBe(230_000);
    expect(parseDollars("0.1")).toBe(10);
    expect(parseDollars("-15.5")).toBe(-1_550);
    expect(parseDollars("12.345")).toBeNull();
    expect(parseDollars("abc")).toBeNull();
  });
});

describe("answering and overruling", () => {
  const agentAnswer = record("r-ans", "agent", {
    kind: "judgment",
    charge_id: "c",
    question: "allowable",
    text: "Is this cost necessary and reasonable, and is it for this project?",
    answer: "unsure",
    reasoning: "The fare class isn't shown.",
  });
  const answers = [{ judgment: agentAnswer, out_of_date: false, rule: null }] as unknown as AnswerView[];
  const question: OpenQuestion = { charge_id: "c", question: "covers", record_id: "r-approval", answer_by: "user" };

  it("answers an open question as a judgment of the accountant's", async () => {
    const onWrite = writer();
    render(<AgentAnswers answers={[]} questions={[question]} rechecking={false} files={{}} chargeId="c" onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Answer" }));
    fireEvent.click(screen.getByLabelText("Supports"));
    fireEvent.change(screen.getByLabelText("Your reasoning"), { target: { value: "The Program Officer approved it in Research.gov." } });
    fireEvent.click(screen.getByRole("button", { name: "Save answer" }));
    await waitFor(() =>
      expect(onWrite).toHaveBeenCalledWith({
        data: {
          kind: "judgment",
          charge_id: "c",
          question: "covers",
          record_id: "r-approval",
          text: "Does this approval cover this charge?",
          answer: "supports",
          reasoning: "The Program Officer approved it in Research.gov.",
        },
        replaces_id: null,
      }),
    );
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save answer" })).toBeNull());
  });

  it("overrules the agent's answer by replacing it", async () => {
    const onWrite = writer();
    render(<AgentAnswers answers={answers} questions={[]} rechecking={false} files={{}} chargeId="c" onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Overrule" }));
    fireEvent.click(screen.getByLabelText("Contradicts"));
    fireEvent.change(screen.getByLabelText("Your reasoning"), { target: { value: "Business class, no exception on file." } });
    fireEvent.click(screen.getByRole("button", { name: "Save answer" }));
    await waitFor(() => expect(onWrite).toHaveBeenCalledTimes(1));
    expect(onWrite.mock.calls[0][0]).toMatchObject({ data: { kind: "judgment", question: "allowable", answer: "contradicts" }, replaces_id: "r-ans" });
  });

  it("asks for an answer and reasoning before writing", () => {
    const onWrite = writer();
    render(<AgentAnswers answers={answers} questions={[]} rechecking={false} files={{}} chargeId="c" onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Overrule" }));
    fireEvent.click(screen.getByRole("button", { name: "Save answer" }));
    expect(screen.getByText("Choose an answer and write your reasoning.")).toBeInTheDocument();
    expect(onWrite).not.toHaveBeenCalled();
  });

  it("calls settling a flag answering it, and changing their own answer a change", () => {
    const flag = record("r-flag", "agent", { kind: "judgment", charge_id: "c", question: "flag", text: "Bought late?", answer: "unsure", reasoning: "11 days left." });
    const own = record("r-own", "user", { kind: "judgment", charge_id: "c", question: "allowable", text: "Allowable?", answer: "supports", reasoning: "Fine." });
    const views = [flag, own].map((judgment) => ({ judgment, out_of_date: false, rule: null })) as unknown as AnswerView[];
    render(<AgentAnswers answers={views} questions={[]} rechecking={false} files={{}} chargeId="c" onWrite={writer()} />);
    expect(screen.getByRole("button", { name: "Answer the flag" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change your answer" })).toBeInTheDocument();
  });
});

describe("changing the checklist", () => {
  const entries: ChecklistEntry[] = [
    { default_item: "participant_list", added_by: "default", needed: "Participant list", filled: false } as ChecklistEntry,
    { item_record_id: "r-item", added_by: "agent", needed: "Honorarium letter", filled: false } as ChecklistEntry,
  ];
  function renderChecklist(onWrite = writer()) {
    render(<EvidenceChecklist checklist={entries} links={[]} waiting={[]} records={{}} files={{}} chargeId="c" onWrite={onWrite} />);
    return onWrite;
  }

  it("adds an item with an amount and an expected date", async () => {
    const onWrite = renderChecklist();
    fireEvent.click(screen.getByRole("button", { name: "Add item" }));
    fireEvent.change(screen.getByLabelText("What's needed"), { target: { value: "Airfare receipt" } });
    fireEvent.change(screen.getByLabelText("Amount (optional)"), { target: { value: "1,800.00" } });
    fireEvent.change(screen.getByLabelText("Expected by (optional)"), { target: { value: "2026-05-01" } });
    fireEvent.click(within(screen.getByRole("form", { name: "Add a checklist item" })).getByRole("button", { name: "Add item" }));
    await waitFor(() =>
      expect(onWrite).toHaveBeenCalledWith({
        data: { kind: "checklist_item", charge_id: "c", needed: "Airfare receipt", amount_cents: 180_000, expected_by: "2026-05-01" },
      }),
    );
  });

  it("refuses an amount it can't read, without writing", () => {
    const onWrite = renderChecklist();
    fireEvent.click(screen.getByRole("button", { name: "Add item" }));
    fireEvent.change(screen.getByLabelText("What's needed"), { target: { value: "Receipt" } });
    fireEvent.change(screen.getByLabelText("Amount (optional)"), { target: { value: "about 20" } });
    fireEvent.click(within(screen.getByRole("form", { name: "Add a checklist item" })).getByRole("button", { name: "Add item" }));
    expect(screen.getByText(/Write the amount as dollars/)).toBeInTheDocument();
    expect(onWrite).not.toHaveBeenCalled();
  });

  it("removes a default item by its key, and an added item by its record", async () => {
    const onWrite = renderChecklist();
    const rows = screen.getAllByRole("listitem");
    fireEvent.click(within(rows[0]).getByRole("button", { name: "Remove" }));
    fireEvent.change(within(rows[0]).getByLabelText("Why (optional)"), { target: { value: "A speaker, not a participant." } });
    fireEvent.click(within(rows[0]).getByRole("button", { name: "Remove item" }));
    await waitFor(() =>
      expect(onWrite).toHaveBeenCalledWith({
        data: { kind: "checklist_removal", charge_id: "c", item_record_id: null, default_item: "participant_list", reason: "A speaker, not a participant." },
      }),
    );
    fireEvent.click(within(rows[1]).getByRole("button", { name: "Remove" }));
    fireEvent.click(within(rows[1]).getByRole("button", { name: "Remove item" }));
    await waitFor(() =>
      expect(onWrite).toHaveBeenLastCalledWith({
        data: { kind: "checklist_removal", charge_id: "c", item_record_id: "r-item", default_item: null, reason: null },
      }),
    );
  });

  it("offers Add item on an empty checklist too", () => {
    render(<EvidenceChecklist checklist={[]} links={[]} waiting={[]} records={{}} files={{}} chargeId="c" onWrite={writer()} />);
    expect(screen.getByRole("button", { name: "Add item" })).toBeInTheDocument();
  });
});

describe("accepting a reason, and snoozing", () => {
  it("accepts a reason with a one-off note by default", async () => {
    const onWrite = writer();
    render(<StatusReasons status={status([reason({})])} onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Accept with a note" }));
    expect(screen.getByLabelText("Just this charge")).toBeChecked();
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Refunded in March." } });
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() =>
      expect(onWrite).toHaveBeenCalledWith({
        data: {
          kind: "accepted_reason",
          charge_id: "c",
          reason: { check: "checklist", problem: "missing_item" },
          note: "Refunded in March.",
          reusable: false,
          rests_on: ["r-item"],
        },
      }),
    );
  });

  it("accepts with a reusable note when chosen", async () => {
    const onWrite = writer();
    render(<StatusReasons status={status([reason({})])} onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Accept with a note" }));
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Monthly facility fee, no invoice." } });
    fireEvent.click(screen.getByLabelText("This and similar charges"));
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(onWrite).toHaveBeenCalledTimes(1));
    expect(onWrite.mock.calls[0][0]).toMatchObject({ data: { reusable: true } });
  });

  it("offers an earlier note with one click, just this charge or this and similar ones", async () => {
    const note = record("r-note", "user", { kind: "accepted_reason", charge_id: "c-april", reason: { check: "checklist", problem: "missing_item" }, note: "Facility fee, no invoice.", reusable: true });
    const onWrite = writer();
    render(<StatusReasons status={status([reason({ offered_note_id: "r-note" })])} records={{ [note.id]: note }} onWrite={onWrite} />);
    const offer = screen.getByTestId("offered-note");
    expect(within(offer).getByText("Facility fee, no invoice.")).toBeInTheDocument();
    fireEvent.click(within(offer).getByRole("button", { name: "Just this charge" }));
    await waitFor(() =>
      expect(onWrite).toHaveBeenCalledWith({
        data: {
          kind: "accepted_reason",
          charge_id: "c",
          reason: { check: "checklist", problem: "missing_item" },
          note: "Facility fee, no invoice.",
          reusable: false,
          reuses_id: "r-note",
          rests_on: ["r-item"],
        },
      }),
    );
    fireEvent.click(within(offer).getByRole("button", { name: "This and similar charges" }));
    await waitFor(() => expect(onWrite).toHaveBeenLastCalledWith(expect.objectContaining({ data: expect.objectContaining({ reusable: true, reuses_id: "r-note" }) })));
  });

  it("reopens a one-off acceptance on this charge with a retraction", async () => {
    const accepted = record("r-acc", "user", { kind: "accepted_reason", charge_id: "c", reason: { check: "checklist", problem: "missing_item" }, note: "Refunded.", reusable: false });
    const onWrite = writer();
    render(<StatusReasons status={status([reason({ accepted_by: "r-acc" })])} records={{ [accepted.id]: accepted }} onWrite={onWrite} />);
    expect(screen.getByText("Your note: Refunded.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept with a note" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    await waitFor(() => expect(onWrite).toHaveBeenCalledWith({ data: { kind: "retraction", reason: null }, replaces_id: "r-acc" }));
  });

  it("doesn't reopen a reusable note from one charge: it covers others too", () => {
    const note = record("r-note", "user", { kind: "accepted_reason", charge_id: "c-april", reason: { check: "checklist", problem: "missing_item" }, note: "Facility fee.", reusable: true });
    render(<StatusReasons status={status([reason({ accepted_by: "r-note" })])} records={{ [note.id]: note }} onWrite={writer()} />);
    expect(screen.getByText(/Under your reusable note/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).toBeNull();
  });

  it("snoozes the charge until a date, covering the reasons chosen", async () => {
    const onWrite = writer();
    const conflict = reason({ check: "period_of_performance", problem: "after_end_date", text: "After the end date.", bucket: "possible_conflict", record_ids: [] });
    render(<StatusReasons status={status([conflict, reason({})])} onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Snooze" }));
    const form = screen.getByRole("form", { name: "Snooze this charge" });
    fireEvent.change(within(form).getByLabelText("Until"), { target: { value: "2026-05-01" } });
    fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Extension notice expected." } });
    fireEvent.click(within(form).getByLabelText("A bill isn't on file."));
    fireEvent.click(within(form).getByRole("button", { name: "Snooze" }));
    await waitFor(() =>
      expect(onWrite).toHaveBeenCalledWith({
        data: {
          kind: "snooze",
          charge_id: "c",
          until: "2026-05-01",
          note: "Extension notice expected.",
          reasons: [{ check: "period_of_performance", problem: "after_end_date" }],
        },
      }),
    );
  });

  it("shows the write check's problems and keeps the form when the server refuses", async () => {
    const onWrite = vi.fn(async () => {
      throw new ApiError(422, ["A snooze can't run past the grant's end date."]);
    });
    render(<StatusReasons status={status([reason({})])} onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Snooze" }));
    const form = screen.getByRole("form", { name: "Snooze this charge" });
    fireEvent.change(within(form).getByLabelText("Until"), { target: { value: "2027-05-01" } });
    fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Later." } });
    fireEvent.click(within(form).getByRole("button", { name: "Snooze" }));
    expect(await screen.findByText("A snooze can't run past the grant's end date.")).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Snooze this charge" })).toBeInTheDocument();
  });
});
