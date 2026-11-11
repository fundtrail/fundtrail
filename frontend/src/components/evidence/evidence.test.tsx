import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  ApiProvider,
  type ApiClient,
  type Citation,
  type EvidenceCard,
  type FactView,
  type FtRecord,
  type NewRecordInput,
} from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FakeAuthProvider } from "@/lib/auth";
import { ConfirmValues } from "./ConfirmValues";
import { EvidenceCardView } from "./EvidenceCardView";
import { fileFacts } from "./fileFacts";
import { fileTags } from "./FileList";
import { findCitation } from "./findCitation";
import { excerptWindow, unionRanges, valueRanges } from "./quote";
import { QuoteLink } from "./QuoteLink";
import { confirmationText, MONEY_KEYS, parseTyped, valueAt, valueLabel, valueType, withValueAt } from "./values";

const GRANT = "grant-sample";

async function sampleCards(): Promise<EvidenceCard[]> {
  return createFakeApiClient().listEvidence(GRANT);
}

function card(cards: EvidenceCard[], name: string): EvidenceCard {
  const c = cards.find((x) => x.file.name === name);
  if (!c) throw new Error(`no card ${name}`);
  return c;
}

describe("values", () => {
  it("reads and replaces values by the server's paths", () => {
    const data = { kind: "bill", items: [{ amount: { value: 5 } }] };
    expect(valueAt(data, "items[0].amount")).toEqual({ value: 5 });
    const next = withValueAt(data, "items[0].amount", { value: 7 });
    expect(valueAt(next, "items[0].amount")).toEqual({ value: 7 });
    expect(valueAt(data, "items[0].amount")).toEqual({ value: 5 });
    expect(valueLabel("items[0].amount")).toBe("Item 1 amount");
    expect(valueLabel("approver_email")).toBe("Approver email");
  });

  it("words each way a value is confirmed", () => {
    expect(confirmationText({ path: "total", confirmed: true, how: "found" })).toBe("Confirmed on the page");
    expect(confirmationText({ path: "total", confirmed: true, how: "record_confirmed", confirmed_at: "2026-03-20T17:00:00Z" })).toBe(
      "Confirmed by the accountant, Mar 20, 2026",
    );
    expect(confirmationText({ path: "total", confirmed: true, how: "typed", confirmed_at: "2026-03-21T17:00:00Z" })).toBe(
      "Confirmed by the accountant, Mar 21, 2026",
    );
    expect(confirmationText({ path: "total", confirmed: false })).toBe("Unconfirmed");
  });

  it("reads typed money as cents", () => {
    expect(parseTyped("money", "$1,240.00")).toEqual({ value: 124000 });
    expect(parseTyped("money", "86.4")).toEqual({ value: 8640 });
    expect(parseTyped("money", "-150")).toEqual({ value: -15000 });
    expect(parseTyped("money", "abc")).toHaveProperty("error");
    expect(parseTyped("date", "2026-03-05")).toEqual({ value: "2026-03-05" });
  });

  it("types a funding notice's amounts as money, so 6,000.00 is $6,000.00 in cents", () => {
    for (const path of ["obligated_by_amendment", "obligated_to_date", "total", "amount", "items[0].amount", "stated_amount", "share.total"]) {
      expect(valueType(path, 100)).toBe("money");
    }
    expect(parseTyped(valueType("obligated_to_date", 12_000_000), "6,000.00")).toEqual({ value: 600_000 });
  });

  // The contract's CitedMoney fields, read from records.py, so a new one can't be missed.
  // Tests run from frontend/.
  const recordsPy = resolve(process.cwd(), "../backend/app/contracts/records.py");
  it.runIf(existsSync(recordsPy))("knows every CitedMoney field in the contract, and no others", () => {
    const fields = new Set([...readFileSync(recordsPy, "utf8").matchAll(/^\s+(\w+): CitedMoney\b/gm)].map((m) => m[1]));
    expect([...MONEY_KEYS].sort()).toEqual([...fields].sort());
  });
});

describe("EvidenceCardView", () => {
  it("lists each fact's values with quote, page and confirmed state", async () => {
    const cards = await sampleCards();
    render(<EvidenceCardView grantId={GRANT} card={card(cards, "field_station_invoice_FS-2207.pdf")} />);
    const total = screen.getByRole("link", { name: "Open total in the viewer" });
    expect(total).toHaveTextContent("Total Due: $3,400.00");
    expect(total).toHaveAttribute("href", "/grants/grant-sample/files/file-syn-field-station-invoice?record=rec-syn-bill-fs-2207&value=total");
    expect(screen.getAllByText("Confirmed on the page").length).toBeGreaterThan(0);
    expect(screen.getByText("p. 2", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Unconfirmed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Confirm or correct the unconfirmed value" })).toHaveAttribute(
      "href",
      "/grants/grant-sample/files/file-syn-field-station-invoice/confirm?record=rec-syn-bill-fs-2207",
    );
  });

  it("says a value the accountant confirmed with the date, instead of 'on the page'", async () => {
    const cards = await sampleCards();
    render(<EvidenceCardView grantId={GRANT} card={card(cards, "budget_justification.docx")} />);
    expect(screen.getByText("Confirmed by the accountant, Mar 20, 2026")).toBeInTheDocument();
    expect(screen.queryByText("Confirmed on the page")).not.toBeInTheDocument();
    expect(screen.getByText("Google Drive")).toBeInTheDocument();
  });

  it("shows the sample bill's link to its charge", async () => {
    const cards = await sampleCards();
    render(<EvidenceCardView grantId={GRANT} card={card(cards, "invoice_1001.txt")} />);
    const links = screen.getByRole("list", { name: "Charges it pays for" });
    expect(within(links).getAllByRole("link")[0].getAttribute("href")).toMatch(/^\/grants\/grant-sample\/charges\//);
  });

  it("puts only a passage found in the file on the highlighter", async () => {
    const cards = await sampleCards();
    render(<EvidenceCardView grantId={GRANT} card={card(cards, "field_station_invoice_FS-2207.pdf")} />);
    // Found in the file: the passage, verbatim, marked.
    const total = screen.getByRole("link", { name: "Open total in the viewer" });
    expect(total.querySelector("mark")).toHaveTextContent("Total Due: $3,400.00");
    // Couldn't be placed: the quote shows plain.
    expect(screen.getByRole("link", { name: "Open dated in the viewer" }).querySelector("mark")).toBeNull();
  });

  it("puts an exact quote on the highlighter, and a close match or one not found plain", async () => {
    const cards = await sampleCards();
    render(<EvidenceCardView grantId={GRANT} card={card(cards, "field_station_invoice_FS-2207.pdf")} />);
    // Exact: on the highlighter, with no note.
    const total = screen.getByRole("link", { name: "Open total in the viewer" });
    expect(total.querySelector("mark")).not.toBeNull();
    // Close: the passage found, but not word for word, so plain, with the viewer's words beside it.
    const description = screen.getByRole("link", { name: "Open description in the viewer" });
    expect(description.querySelector("mark")).toBeNull();
    expect(description.parentElement).toHaveTextContent("Close match on the page");
    // Not found: plain, and no close-match note.
    const dated = screen.getByRole("link", { name: "Open dated in the viewer" });
    expect(dated.querySelector("mark")).toBeNull();
    expect(dated.parentElement).not.toHaveTextContent("Close match on the page");
    expect(screen.getAllByText("Close match on the page")).toHaveLength(1);
  });

  it("says a passage once when several values of a record cite it", async () => {
    const cards = await sampleCards();
    render(<EvidenceCardView grantId={GRANT} card={card(cards, "award_letter.txt")} />);
    const rule = screen.getByRole("listitem", { name: /^Approval rule/ });
    // Four values cite the same special-conditions passage; it shows once.
    expect(within(rule).getAllByText(/Special conditions/)).toHaveLength(1);
    // Each value still opens its own spot in the viewer.
    for (const path of ["applies_to", "approver", "channel", "scope"]) {
      const label = valueLabel(path).toLowerCase();
      expect(within(rule).getByRole("link", { name: `Open ${label} in the viewer` }).getAttribute("href")).toMatch(
        new RegExp(`value=${path}$`),
      );
    }
  });

  it("never puts a photo's box on the highlighter, as it has no passage", async () => {
    const cards = await sampleCards();
    render(<EvidenceCardView grantId={GRANT} card={card(cards, "boat_rental_receipt.jpg")} />);
    const total = screen.getByRole("link", { name: "Open total in the viewer" });
    expect(total).toHaveTextContent("A box on the image");
    expect(total.querySelector("mark")).toBeNull();
  });
});

describe("QuoteLink", () => {
  const LINES = [
    "Special conditions apply to every amount budgeted on this award.",
    "Funds budgeted for one category may not be moved to another category",
    "of expense without the prior written approval of the cognizant",
    "Program Officer, requested through the agency's online system.",
  ];
  const PASSAGE = LINES.join("\n");
  const START = 400;
  const cite = (passage: string, value: string | null, match: "exact" | "close" = "exact") => {
    const at = value === null ? -1 : passage.indexOf(value);
    return {
      file_id: "f",
      passage,
      location: { type: "char_location" as const, start_char_index: START, end_char_index: START + passage.length },
      match,
      highlight: value === null ? null : [{ start_char_index: START + at, end_char_index: START + at + value.length }],
    };
  };

  it("shows the part of a long quote that holds the value, even on its fourth line", () => {
    render(<QuoteLink citation={cite(PASSAGE, "Program Officer")} href="/v" ariaLabel="Open approver in the viewer" />);
    const shown = screen.getByTestId("card-quote");
    // The value is in view and set stronger; the cut is marked with an ellipsis.
    expect(shown).toHaveTextContent("Program Officer");
    expect(shown.querySelector("strong")).toHaveTextContent(/^Program Officer$/);
    expect(shown.textContent?.startsWith("…")).toBe(true);
    expect(shown).not.toHaveTextContent("Special conditions apply");
    // The whole quote opens in place.
    fireEvent.click(screen.getByRole("button", { name: "Show the whole quote" }));
    expect(screen.getByTestId("card-quote").textContent).toBe(PASSAGE);
    expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true");
  });

  it("never clamps a long quote when the value's place in it isn't known", () => {
    render(<QuoteLink citation={cite(PASSAGE, null)} href="/v" ariaLabel="Open approver in the viewer" />);
    expect(screen.getByTestId("card-quote").textContent).toBe(PASSAGE);
    expect(screen.queryByRole("button", { name: "Show the whole quote" })).toBeNull();
  });

  it("shows a short quote whole, with the value stronger", () => {
    const short = "Total Due: $1,240.00";
    render(<QuoteLink citation={cite(short, "$1,240.00")} href="/v" ariaLabel="Open total in the viewer" />);
    expect(screen.getByTestId("card-quote").textContent).toBe(short);
    expect(screen.getByTestId("card-quote").querySelector("strong")).toHaveTextContent("$1,240.00");
    expect(screen.queryByRole("button")).toBeNull();
  });

  // The award letter's special-conditions passage, with each value's own
  // characters stored as the server would store them.
  const RULE =
    "Special conditions: Funds budgeted for Participant Support Costs may not be diverted by the awardee to other categories of expense without the prior written approval of the cognizant NSF Program Officer, requested through Research.gov.";
  const RULE_VALUES = [
    "Participant Support Costs",
    "Program Officer",
    "Research.gov",
    "may not be diverted by the awardee to other categories of expense",
  ];

  it("shows a passage several values share whole when their places span more than one excerpt", () => {
    const ranges = unionRanges(RULE_VALUES.map((v) => valueRanges(cite(RULE, v))));
    render(<QuoteLink citation={cite(RULE, RULE_VALUES[0])} href="/v" ariaLabel="Open the passage" ranges={ranges} />);
    const shown = screen.getByTestId("card-quote");
    expect(shown.textContent).toBe(RULE);
    for (const v of RULE_VALUES) expect(shown).toHaveTextContent(v);
    expect([...shown.querySelectorAll("strong")].map((s) => s.textContent)).toEqual(RULE_VALUES.slice().sort((a, b) => RULE.indexOf(a) - RULE.indexOf(b)));
    expect(screen.queryByRole("button", { name: "Show the whole quote" })).toBeNull();
  });

  it("shows a shared passage whole when one value's place isn't known", () => {
    const ranges = unionRanges([valueRanges(cite(PASSAGE, "Program Officer")), valueRanges(cite(PASSAGE, null))]);
    expect(ranges).toBeNull();
    render(<QuoteLink citation={cite(PASSAGE, "Program Officer")} href="/v" ariaLabel="Open the passage" ranges={ranges} />);
    expect(screen.getByTestId("card-quote").textContent).toBe(PASSAGE);
    expect(screen.queryByRole("button", { name: "Show the whole quote" })).toBeNull();
  });

  it("shows a value whose characters sit far apart in the quote whole", () => {
    const at = (s: string) => START + PASSAGE.indexOf(s);
    const c = {
      ...cite(PASSAGE, null),
      highlight: [
        { start_char_index: at("Special"), end_char_index: at("Special") + "Special".length },
        { start_char_index: at("Program Officer"), end_char_index: at("Program Officer") + "Program Officer".length },
      ],
    };
    expect(excerptWindow(PASSAGE, valueRanges(c))).toBeNull();
    render(<QuoteLink citation={c} href="/v" ariaLabel="Open approver in the viewer" />);
    const shown = screen.getByTestId("card-quote");
    expect(shown.textContent).toBe(PASSAGE);
    expect([...shown.querySelectorAll("strong")].map((s) => s.textContent)).toEqual(["Special", "Program Officer"]);
  });

  it("reads no place for the value when the passage isn't the stored characters", () => {
    const c = cite(PASSAGE, "Program Officer");
    expect(valueRanges(c)).not.toBeNull();
    // A reading-text passage of a different length: stored positions don't count in it.
    expect(valueRanges({ ...c, passage: `${PASSAGE} (forwarded)` })).toBeNull();
    expect(excerptWindow(PASSAGE, null)).toBeNull();
  });
});

describe("the file list's tags", () => {
  it("says a copy as the card says it, whole, with the copy mark's state while it waits", async () => {
    const cards = await sampleCards();
    const base = card(cards, "invoice_1001.txt");
    const original = card(cards, "award_letter.txt").file;
    const copy: EvidenceCard = {
      ...base,
      duplicate: {
        mark: { ...base.facts![0].record, id: "rec-dup", data: { kind: "duplicate", copy_file_id: base.file.id, original_file_id: original.id } },
        state: "waiting",
      } as EvidenceCard["duplicate"],
      files: { [original.id]: original },
    };
    expect(fileTags(copy).map((t) => t.text)).toContain("Copy of award_letter.txt · Waiting for the accountant");
    // While the mark waits the card offers Confirm and Reject, which write through the API.
    render(withApi({}, <EvidenceCardView grantId={GRANT} card={copy} />));
    expect(screen.getByText("Copy of award_letter.txt · Waiting for the accountant")).toBeInTheDocument();
    // Once the copy counts, both say only what it is.
    const counted = { ...copy, duplicate: { ...copy.duplicate!, state: "counts" as const } };
    expect(fileTags(counted).map((t) => t.text)).toContain("Copy of award_letter.txt");
  });
});

describe("In this file", () => {
  it("lists only the values whose citation is in this file", () => {
    const cite = (fileId: string, passage: string) => ({
      file_id: fileId,
      passage,
      location: { type: "char_location" as const, start_char_index: 0, end_char_index: passage.length },
      match: "exact" as const,
    });
    // One record whose values cite two files: it's on both files' cards.
    const record = {
      id: "rec-two-files",
      data: {
        kind: "bill",
        total: { value: 12_000, text: "$120.00", citation: cite("file-a", "Total: $120.00") },
        vendor: { value: "Example Supply", text: "Example Supply", citation: cite("file-b", "Example Supply") },
        dated: { value: "2026-03-01", text: "March 1, 2026", citation: null, uncited: true },
      },
    } as unknown as FtRecord;
    const onA = {
      file: { id: "file-a", name: "a.txt" },
      facts: [
        {
          record,
          state: "counts",
          values: [
            { path: "total", confirmed: true },
            { path: "vendor", confirmed: true },
            { path: "dated", confirmed: false },
          ],
        },
      ],
    } as unknown as EvidenceCard;
    const groups = fileFacts(GRANT, onA, { recordId: "rec-two-files", value: "total" });
    expect(groups).toHaveLength(1);
    expect(groups[0].values.map((v) => v.label)).toEqual(["Total"]);
    expect(groups[0].values[0].href).toBe("/grants/grant-sample/files/file-a?record=rec-two-files&value=total");
    expect(groups[0].values[0].current).toBe(true);
    // On the other file's card, only the value from that file.
    const onB = { ...onA, file: { id: "file-b", name: "b.txt" } } as unknown as EvidenceCard;
    expect(fileFacts(GRANT, onB, { recordId: null, value: null })[0].values.map((v) => v.label)).toEqual(["Vendor"]);
  });
});

describe("findCitation", () => {
  it("finds a fact's value and a link's part", async () => {
    const cards = await sampleCards();
    const spot = findCitation(cards, "rec-syn-bill-boat-receipt", "total");
    expect(spot?.valueText).toBe("$86.40");
    expect(spot?.citation.location.type).toBe("image_box");
    expect(findCitation(cards, "rec-missing", "total")).toBeNull();
  });

  // An answer (a judgment record) isn't on the cards; its quotes are found in the grant's records.
  const quote = (passage: string): Citation => ({
    file_id: "file-award-letter",
    passage,
    location: { type: "char_location", start_char_index: 10, end_char_index: 10 + passage.length },
    match: "exact",
  });
  const answer = {
    id: "rec-answer-1",
    data: {
      kind: "judgment",
      question: "allowable",
      text: "Is this travel allowable?",
      answer: "supports",
      reasoning: "The award letter allows it.",
      quotes: [quote("Travel is allowable."), quote("Prior approval is not needed.")],
    },
  } as unknown as FtRecord;

  it("finds an answer's quote by its index", async () => {
    const cards = await sampleCards();
    const spot = findCitation(cards, "rec-answer-1", "quotes[1]", [answer]);
    expect(spot?.citation.passage).toBe("Prior approval is not needed.");
    expect(spot?.label).toBe("Quote 2 in the answer");
    expect(spot?.valueText).toBeNull();
    expect(spot?.confirmation).toBeNull();
  });

  it("falls back as before for an index out of range or a record that isn't an answer", async () => {
    const cards = await sampleCards();
    expect(findCitation(cards, "rec-answer-1", "quotes[2]", [answer])).toBeNull();
    expect(findCitation(cards, "rec-answer-1", "total", [answer])).toBeNull();
    const notAnswer = { ...answer, id: "rec-note-1", data: { ...(answer.data as object), kind: "note" } } as unknown as FtRecord;
    expect(findCitation(cards, "rec-note-1", "quotes[0]", [notAnswer])).toBeNull();
    // Without the records, an answer's quote isn't found, as before.
    expect(findCitation(cards, "rec-answer-1", "quotes[0]")).toBeNull();
    // A fact on the cards is still found from the cards, records or not.
    expect(findCitation(cards, "rec-syn-bill-boat-receipt", "total", [answer])?.valueText).toBe("$86.40");
  });
});

function withApi(client: Partial<ApiClient>, children: ReactNode) {
  return (
    <FakeAuthProvider>
      <ApiProvider client={client as ApiClient}>{children}</ApiProvider>
    </FakeAuthProvider>
  );
}

async function photoFact(): Promise<FactView> {
  return card(await sampleCards(), "boat_rental_receipt.jpg").facts![0];
}

function written(record: Partial<FtRecord>): FtRecord {
  return { id: "rec-new", workspace_id: "ws", grant_id: GRANT, author: "user", written_at: "2026-04-09T18:00:00Z", data: { kind: "confirmation", record_ids: [] }, ...record } as FtRecord;
}

describe("ConfirmValues", () => {
  it("lists each value that couldn't be found", async () => {
    const fact = await photoFact();
    render(withApi({}, <ConfirmValues grantId={GRANT} fileId="f" fact={fact} onDone={() => {}} />));
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("group", { name: "Vendor" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Dated" })).toBeInTheDocument();
  });

  it("says that saving accepts the whole record when it's still waiting", async () => {
    const fact = await photoFact();
    const { rerender } = render(withApi({}, <ConfirmValues grantId={GRANT} fileId="f" fact={fact} onDone={() => {}} />));
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    rerender(withApi({}, <ConfirmValues grantId={GRANT} fileId="f" fact={{ ...fact, state: "waiting" }} onDone={() => {}} />));
    expect(screen.getByRole("note")).toHaveTextContent("Saving accepts the whole record");
  });

  it("confirms as read with one confirmation of the record", async () => {
    const fact = await photoFact();
    const writeRecord = vi.fn<ApiClient["writeRecord"]>(async () => written({}));
    const onDone = vi.fn();
    render(withApi({ writeRecord }, <ConfirmValues grantId={GRANT} fileId="f" fact={fact} onDone={onDone} />));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(writeRecord).toHaveBeenCalledTimes(1);
    expect(writeRecord.mock.calls[0][1]).toEqual({ data: { kind: "confirmation", record_ids: [fact.record.id], decision: "confirmed" } });
  });

  it("writes one replacing record: the typed value with no citation, the value left as read with its citation", async () => {
    const fact = await photoFact();
    const writeRecord = vi.fn<ApiClient["writeRecord"]>(async (_grantId, body: NewRecordInput) => written({ id: "rec-typed", replaces_id: body.replaces_id }));
    const onDone = vi.fn();
    render(withApi({ writeRecord }, <ConfirmValues grantId={GRANT} fileId="f" fact={fact} onDone={onDone} />));
    const vendor = screen.getByRole("group", { name: "Vendor" });
    fireEvent.click(within(vendor).getByLabelText("Type the right value"));
    fireEvent.change(screen.getByLabelText("The right vendor"), { target: { value: "Example Bay Boat Rental" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());

    const replacement = writeRecord.mock.calls[0][1];
    expect(replacement.replaces_id).toBe(fact.record.id);
    expect(valueAt(replacement.data, "vendor")).toEqual({ value: "Example Bay Boat Rental", text: null, citation: null, uncited: false });
    // "Dated" was left as read: it keeps the agent's citation, so its highlight still shows.
    const dated = valueAt(fact.record.data, "dated") as { citation: unknown };
    expect(dated.citation).not.toBeNull();
    expect(valueAt(replacement.data, "dated")).toEqual(dated);
    expect(valueAt(replacement.data, "total")).toEqual(valueAt(fact.record.data, "total"));
    // The accountant's own record is their confirmation: no second write.
    expect(writeRecord).toHaveBeenCalledTimes(1);
  });

  it("shows the write check's problems as the server words them", async () => {
    const fact = await photoFact();
    const writeRecord = vi.fn(async () => {
      throw new ApiError(422, ["The record isn't waiting for a confirmation."]);
    });
    render(withApi({ writeRecord }, <ConfirmValues grantId={GRANT} fileId="f" fact={fact} onDone={() => {}} />));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The record isn't waiting for a confirmation.");
  });

  it("refuses a typed amount it can't read, before writing anything", async () => {
    const fact = card(await sampleCards(), "field_station_invoice_FS-2207.pdf").facts![0];
    const writeRecord = vi.fn();
    render(withApi({ writeRecord }, <ConfirmValues grantId={GRANT} fileId="f" fact={fact} onDone={() => {}} />));
    fireEvent.click(screen.getByLabelText("Type the right value"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Type a value, or choose to confirm it as read.")).toBeInTheDocument();
    expect(writeRecord).not.toHaveBeenCalled();
  });
});
