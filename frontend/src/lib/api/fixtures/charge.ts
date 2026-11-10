// The charge page for the sample grant's two charges. Owned by the charge
// screen's builder.

import type { ApiClient } from "../client";
import type { AnswerView, BudgetCategory, BudgetLine, ChargeDetail, EvidenceFile, FtRecord, HistoryEntry, Id, Judgment, Link, LinkView } from "../types";
import { chargeStatusAt } from "./statuses";
import { sampleThreads } from "./thread";
import { foundValues, sampleCharge, sampleFile, sampleRecord, served } from "./sample";

function linkView(linkId: Id, fileId: Id): LinkView {
  const link = sampleRecord<FtRecord<Link>>(linkId);
  const record = sampleRecord(link.data.record_id);
  return {
    link,
    record,
    values: foundValues(record),
    file: sampleFile(fileId),
  };
}

function answer(id: Id): AnswerView {
  return { judgment: sampleRecord<FtRecord<Judgment>>(id), out_of_date: false, rule: null };
}

function detail(args: {
  chargeId: Id;
  budgetLineId: Id;
  categories: BudgetCategory[];
  history: HistoryEntry[];
  link: LinkView;
  answer: AnswerView;
}): ChargeDetail {
  const records: Record<Id, FtRecord> = {};
  for (const r of [args.link.link, args.link.record, args.answer.judgment, sampleRecord("rec-period")]) records[r.id] = r;
  const files: Record<Id, EvidenceFile> = {};
  if (args.link.file) files[args.link.file.id] = args.link.file;
  return {
    charge: sampleCharge(args.chargeId),
    status: chargeStatusAt(args.chargeId),
    budget_line: sampleRecord<FtRecord<BudgetLine>>(args.budgetLineId),
    account_categories: args.categories,
    corrections: [],
    history: args.history,
    links: [args.link],
    answers: [args.answer],
    questions: [],
    waiting: [],
    thread: sampleThreads().charges[args.chargeId],
    records,
    files,
  };
}

export function sampleChargeDetails(): Record<Id, ChargeDetail> {
  return {
    "chg-l-1001": detail({
      chargeId: "chg-l-1001",
      budgetLineId: "rec-budget-materials-and-supplies",
      categories: ["materials_and_supplies"],
      history: [
        {
          entry: { changed_at: "2025-11-14T00:00:00Z", trigger: { kind: "charge", id: "chg-l-1001" }, status: chargeStatusAt("chg-l-1001") },
          text: "ledger line L-1001 arrived",
        },
      ],
      link: linkView("rec-link-l-1001", "file-invoice-1001"),
      answer: answer("rec-allowable-l-1001"),
    }),
    "chg-l-1002": detail({
      chargeId: "chg-l-1002",
      budgetLineId: "rec-budget-other",
      categories: ["other_direct_costs_other"],
      history: [
        {
          entry: { changed_at: "2026-02-24T00:00:00Z", trigger: { kind: "charge", id: "chg-l-1002" }, status: chargeStatusAt("chg-l-1002") },
          text: "ledger line L-1002 arrived",
        },
      ],
      link: linkView("rec-link-l-1002", "file-sequencing-statement"),
      answer: answer("rec-allowable-l-1002"),
    }),
  };
}

export function chargeFake(): Pick<ApiClient, "getCharge"> {
  const details = sampleChargeDetails();
  return { getCharge: (chargeId) => served(details[chargeId]) };
}
