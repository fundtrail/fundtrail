import { describe, expect, it } from "vitest";
import type { TextSegment } from "@/lib/api/types";
import { mapSpanToReading, mapSpansToReading } from "./reading";

// A stored email and the text the agent reads: the Date header is replaced by
// the grant's date (a longer line), the Message-ID header is dropped, and the
// body is kept as it is.
const STORED = [
  "From: robin.example@university.example", // 0..38, newline at 38
  "Date: Sat, 21 Feb 2026 09:12:00 -0800", // 39..76, newline at 76
  "Message-ID: <synthetic-0001@university.example>", // 77..124, newline at 124
  "Subject: Usage statement SEQ-0207", // 125..158
  "",
  "Total: $2,180.00",
].join("\n");

const READING = [
  "From: robin.example@university.example",
  "Date: Tuesday, February 24, 2026 at 00:00 UTC",
  "Subject: Usage statement SEQ-0207",
  "",
  "Total: $2,180.00",
].join("\n");

const fromLen = "From: robin.example@university.example\n".length; // 39
const storedSubject = STORED.indexOf("Subject:");
const readingSubject = READING.indexOf("Subject:");

const SEGMENTS: TextSegment[] = [
  { stored_start: 0, reading_start: 0, length: fromLen },
  { stored_start: storedSubject, reading_start: readingSubject, length: STORED.length - storedSubject },
];

const slice = (text: string, span: { start: number; end: number } | null) => (span ? text.slice(span.start, span.end) : null);

describe("mapSpanToReading", () => {
  it("moves a highlight inside a kept span with the span", () => {
    const start = STORED.indexOf("robin.example");
    const span = mapSpanToReading({ start, end: start + "robin.example".length }, SEGMENTS, READING);
    expect(slice(READING, span)).toBe("robin.example");
  });

  it("shifts a highlight after a header that was replaced by a longer line", () => {
    const start = STORED.indexOf("$2,180.00");
    const span = mapSpanToReading({ start, end: start + "$2,180.00".length }, SEGMENTS, READING);
    expect(span?.start).not.toBe(start);
    expect(slice(READING, span)).toBe("$2,180.00");
  });

  it("runs across a gap, taking in the replaced line between", () => {
    const start = STORED.indexOf("university.example");
    const end = STORED.indexOf("Subject:") + "Subject:".length;
    const span = mapSpanToReading({ start, end }, SEGMENTS, READING);
    expect(slice(READING, span)).toBe("university.example\nDate: Tuesday, February 24, 2026 at 00:00 UTC\nSubject:");
  });

  it("highlights the replaced line for a range that falls in a gap", () => {
    const start = STORED.indexOf("21 Feb 2026");
    const span = mapSpanToReading({ start, end: start + "21 Feb 2026".length }, SEGMENTS, READING);
    expect(slice(READING, span)).toBe("Date: Tuesday, February 24, 2026 at 00:00 UTC");
  });

  it("highlights nothing for a dropped header with no line in its place", () => {
    // Only the From line is kept, and nothing replaces what follows it.
    const dropped: TextSegment[] = [{ stored_start: 0, reading_start: 0, length: fromLen }];
    const reading = STORED.slice(0, fromLen);
    const start = STORED.indexOf("synthetic-0001");
    expect(mapSpanToReading({ start, end: start + 5 }, dropped, reading)).toBeNull();
  });

  it("counts code points, as the server does", () => {
    const stored = "\u{1F600} Total: $5";
    const reading = "Date: today\n\u{1F600} Total: $5";
    const segments: TextSegment[] = [{ stored_start: 0, reading_start: 12, length: 12 }];
    const span = mapSpanToReading({ start: 2, end: 7 }, segments, reading);
    expect(span).toEqual({ start: 14, end: 19 });
    expect(Array.from(stored).slice(2, 7).join("")).toBe("Total");
  });
});

describe("mapSpansToReading", () => {
  it("keeps each highlight that lands somewhere", () => {
    const a = STORED.indexOf("SEQ-0207");
    const spans = mapSpansToReading([{ start: a, end: a + 8 }], SEGMENTS, READING);
    expect(spans.map((s) => READING.slice(s.start, s.end))).toEqual(["SEQ-0207"]);
  });
});
