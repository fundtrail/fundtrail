"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { BoxOverlay } from "./BoxOverlay";
import type { ReadingView } from "@/lib/api/types";
import { placeCitation, zoomForBoxes, type Box, type CitationLike, type Placement } from "./placement";
import { mapSpansToReading, passageInReading } from "./reading";
import { splitBySpans } from "./textSpans";
import styles from "./viewer.module.css";

const PdfPages = dynamic(() => import("./PdfPages"), {
  ssr: false,
  loading: () => <p className="ft-empty">Loading the PDF viewer…</p>,
});

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export type FileKind = "text" | "pdf" | "image" | "docx" | "other";

/** How the viewer shows a file, from its media type (and its name, for a .docx sent as a generic type). */
export function fileKind(mediaType: string, name = ""): FileKind {
  const type = mediaType.toLowerCase();
  if (type === DOCX || name.toLowerCase().endsWith(".docx")) return "docx";
  if (type.startsWith("text/") || type === "message/rfc822") return "text";
  if (type === "application/pdf") return "pdf";
  if (type.startsWith("image/")) return "image";
  return "other";
}

/** The base width of a page at 100%, in CSS pixels. */
const PAGE_WIDTH = 760;
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3];

function stepZoom(current: number, dir: 1 | -1): number {
  const next = dir > 0 ? ZOOMS.find((z) => z > current + 1e-9) : [...ZOOMS].reverse().find((z) => z < current - 1e-9);
  return next ?? current;
}

/** What the viewer says about the spot, in the side panel and the bar. */
function placementCaption(p: Placement | null, match: CitationLike["match"]): string {
  if (!p) return "No fact selected";
  if (p.kind === "unplaced") return "Couldn't be placed in the file";
  if (p.kind === "boxes" && p.passage === null) return "Box checked by a second look";
  return match === "close" ? "Close match on the page" : "Exact passage";
}

export interface ViewerProps {
  file: { name: string; media_type: string };
  /** The short-lived link to the original (GET /evidence/{file_id}/content). */
  url: string;
  /** The citation to open at; null opens the file at the top with nothing highlighted. */
  citation: CitationLike | null;
  /** The value as the document writes it. The quote for a photo or scan, which has no passage. */
  valueText?: string | null;
  /** What the value is, for example "Total". */
  label?: string | null;
  /**
   * The value's state from its evidence card (the server's ValueState, worded
   * as the card words it). The viewer never works it out from the citation:
   * a value the accountant confirmed is confirmed even when it couldn't be placed.
   */
  confirmation?: { confirmed: boolean; text: string } | null;
  /**
   * The text the agent reads, for an email on a sample grant (FileLink.reading,
   * ruling 45). When set, the viewer shows it in place of the stored email and
   * carries each highlight into it; the original stays downloadable from `url`.
   */
  reading?: ReadingView | null;
}

/**
 * The full original, opened at a fact's spot (product.md, Viewer): the exact
 * characters highlighted for text, email and .docx; boxes on a PDF page, a
 * photo or a scan; and for a fact that couldn't be placed, its page with the
 * quote beside it and nothing highlighted. It draws only what the server
 * stored, and guesses nothing.
 */
export function Viewer({ file, url, citation, valueText = null, label = null, confirmation = null, reading = null }: ViewerProps) {
  const kind = fileKind(file.media_type, file.name);
  const placement = useMemo(() => (citation ? placeCitation(citation, valueText) : null), [citation, valueText]);
  const boxes = placement?.kind === "boxes" ? placement.boxes : [];
  const [zoom, setZoom] = useState(() => zoomForBoxes(boxes));
  const scrollRef = useRef<HTMLDivElement>(null);
  const [readyTick, setReadyTick] = useState(0);
  const onReady = useCallback(() => setReadyTick((t) => t + 1), []);

  // Scroll to the spot once something has drawn, and again after a zoom.
  useEffect(() => {
    const target = scrollRef.current?.querySelector<HTMLElement>('[data-scroll-target="true"]');
    // A whole page opens at its top; a highlight opens in the middle of the view.
    const whole = target?.hasAttribute("data-page");
    target?.scrollIntoView?.(whole ? { block: "start", inline: "start" } : { block: "center", inline: "center" });
  }, [readyTick, zoom]);

  let body: ReactNode;
  if (kind === "text" && reading) {
    body = <ReadingText url={url} reading={reading} placement={placement} zoom={zoom} onReady={onReady} />;
  } else if (kind === "text") {
    body = <TextFile url={url} placement={placement} zoom={zoom} onReady={onReady} />;
  } else if (kind === "docx") {
    body = <DocxPassage url={url} placement={placement} zoom={zoom} reading={reading} />;
  } else if (kind === "pdf") {
    body = <PdfFile url={url} placement={placement} zoom={zoom} onReady={onReady} />;
  } else if (kind === "image") {
    body = <ImageFile url={url} name={file.name} boxes={boxes} zoom={zoom} onReady={onReady} />;
  } else {
    body = (
      <p className="ft-empty">
        This kind of file can&apos;t be shown here.{" "}
        <a className="ft-link" href={url} target="_blank" rel="noreferrer">
          Open the original
        </a>
      </p>
    );
  }

  const quote = placement?.kind === "unplaced" ? placement.quote : (citation?.passage ?? valueText);

  return (
    <div className={styles.viewer}>
      <section className={styles.doc} aria-label={`Viewer: ${file.name}`}>
        <div className={styles.bar}>
          <span className="ft-heading">{file.name}</span>
          <div className={styles.zoom}>
            <button type="button" className="ft-btn ft-btn--sm" onClick={() => setZoom((z) => stepZoom(z, -1))} aria-label="Zoom out">
              −
            </button>
            <span className="ft-caption ft-num" aria-live="polite">
              {Math.round(zoom * 100)}%
            </span>
            <button type="button" className="ft-btn ft-btn--sm" onClick={() => setZoom((z) => stepZoom(z, 1))} aria-label="Zoom in">
              +
            </button>
          </div>
        </div>
        <div className={styles.scroll} ref={scrollRef} data-testid="viewer-scroll">
          {body}
        </div>
      </section>

      {citation && (
        <aside className={styles.side} aria-label="The quote">
          <span className="ft-label">{label ?? "Quote"}</span>
          {valueText && <span className="ft-strong">{valueText}</span>}
          <span className="ft-caption">{placementCaption(placement, citation.match)}</span>
          {confirmation && (
            <span className="ft-caption" data-testid="value-state">
              {confirmation.text}
            </span>
          )}
          {placement?.kind === "unplaced" && (
            <p className={styles.notice} role="note">
              Nothing is highlighted: this value couldn&apos;t be placed in the file
              {confirmation && !confirmation.confirmed ? ", so it's unconfirmed." : "."}
              {placement.page !== null && ` The viewer is open at page ${placement.page}.`}
            </p>
          )}
          {quote && (
            <blockquote className={styles.quote} data-testid="side-quote">
              {quote}
            </blockquote>
          )}
        </aside>
      )}
    </div>
  );
}

// --- Text, email -------------------------------------------------------------

function useText(url: string) {
  const [state, setState] = useState<{ url: string; text?: string; failed?: boolean }>({ url });
  useEffect(() => {
    let live = true;
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.arrayBuffer();
      })
      // Decoded the way the server decodes it for the model (agent/files.py:
      // UTF-8, bad bytes replaced), keeping a leading byte order mark so the
      // server's character indexes still line up. Response.text() would drop it.
      .then((bytes) => new TextDecoder("utf-8", { ignoreBOM: true }).decode(bytes))
      .then(
        (text) => live && setState({ url, text }),
        () => live && setState({ url, failed: true }),
      );
    return () => {
      live = false;
    };
  }, [url]);
  return state.url === url ? state : { url };
}

function TextFile({
  url,
  placement,
  zoom,
  onReady,
}: {
  url: string;
  placement: Placement | null;
  zoom: number;
  onReady: () => void;
}) {
  const { text, failed } = useText(url);
  useEffect(() => {
    if (text !== undefined) onReady();
  }, [text, onReady]);

  if (failed) return <p className="ft-error">Couldn&apos;t load this file.</p>;
  if (text === undefined) return <p className="ft-empty">Loading the file…</p>;
  const spans = placement?.kind === "text" ? placement.spans : [];
  return <MarkedText text={text} spans={spans} offset={0} zoom={zoom} />;
}

/** An email on a sample grant, shown as the agent reads it, with the highlights carried over. */
function ReadingText({
  url,
  reading,
  placement,
  zoom,
  onReady,
}: {
  url: string;
  reading: ReadingView;
  placement: Placement | null;
  zoom: number;
  onReady: () => void;
}) {
  useEffect(() => onReady(), [reading, onReady]);
  const spans = useMemo(
    () => (placement?.kind === "text" ? mapSpansToReading(placement.spans, reading.segments, reading.text) : []),
    [placement, reading],
  );
  return (
    <div>
      <p className="ft-caption" style={{ marginBottom: "var(--space-3)" }} data-testid="reading-note">
        Shown as the agent reads it, with the grant&apos;s date.{" "}
        <a className="ft-link" href={url} download>
          Download the original
        </a>
      </p>
      <MarkedText text={reading.text} spans={spans} offset={0} zoom={zoom} />
    </div>
  );
}

function MarkedText({
  text,
  spans,
  offset,
  zoom,
}: {
  text: string;
  spans: { start: number; end: number }[];
  offset: number;
  zoom: number;
}) {
  const pieces = splitBySpans(text, spans, offset);
  return (
    <pre className={styles.text} style={{ fontSize: `${13 * zoom}px` }} data-testid="viewer-text">
      {pieces.map((p, i) =>
        p.marked ? (
          <mark key={i} className={styles.mark} data-scroll-target={p.first ? "true" : undefined}>
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </pre>
  );
}

// --- .docx -------------------------------------------------------------------

/**
 * A browser can't show a .docx, and its character indexes count in the text
 * the server extracted, which no endpoint serves yet. So the viewer shows the
 * cited passage, which is that text, with the exact characters highlighted, and
 * links to the original.
 */
function DocxPassage({
  url,
  placement,
  zoom,
  reading = null,
}: {
  url: string;
  placement: Placement | null;
  zoom: number;
  reading?: ReadingView | null;
}) {
  return (
    <div>
      <p className="ft-caption" style={{ marginBottom: "var(--space-3)" }}>
        A Word file (.docx) can&apos;t be shown in the browser. This is the quoted passage from the file&apos;s text.{" "}
        <a className="ft-link" href={url} download>
          Download the original
        </a>
      </p>
      {placement?.kind === "text" ? (
        <PassageText placement={placement} reading={reading} zoom={zoom} />
      ) : placement?.kind === "unplaced" && placement.quote ? (
        <MarkedText text={placement.quote} spans={[]} offset={0} zoom={zoom} />
      ) : null}
    </div>
  );
}

/**
 * Just the cited passage, highlighted. On a sample grant (ruling 50) the passage
 * is reading text while the highlights stay in stored positions, so they're
 * carried into the reading text first, and the passage's start with them.
 */
export function PassageText({
  placement,
  reading,
  zoom,
}: {
  placement: Extract<Placement, { kind: "text" }>;
  reading: ReadingView | null;
  zoom: number;
}) {
  const { spans, offset } = reading
    ? passageInReading(placement.spans, placement.passageStart, reading.segments, reading.text)
    : { spans: placement.spans, offset: placement.passageStart };
  return <MarkedText text={placement.passage} spans={spans} offset={offset} zoom={zoom} />;
}

// --- PDF ---------------------------------------------------------------------

function PdfFile({
  url,
  placement,
  zoom,
  onReady,
}: {
  url: string;
  placement: Placement | null;
  zoom: number;
  onReady: () => void;
}) {
  const boxes = useMemo(() => (placement?.kind === "boxes" ? placement.boxes : []), [placement]);
  // A PDF match with no stored boxes opens at its page too, with nothing outlined.
  const targetPage = placement?.kind === "unplaced" ? placement.page : null;
  const overlay = useCallback(
    (page: number) => <BoxOverlay boxes={boxes.filter((b) => b.page === page)} first={boxes[0] ?? null} />,
    [boxes],
  );
  return <PdfPages url={url} width={PAGE_WIDTH * zoom} overlay={overlay} targetPage={targetPage} onPageReady={onReady} />;
}

// --- Photo or scan -----------------------------------------------------------

function ImageFile({
  url,
  name,
  boxes,
  zoom,
  onReady,
}: {
  url: string;
  name: string;
  boxes: Box[];
  zoom: number;
  onReady: () => void;
}) {
  return (
    <div className={styles.page} style={{ width: `${PAGE_WIDTH * zoom}px` }}>
      {/* eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link, not a static asset */}
      <img src={url} alt={name} onLoad={onReady} />
      <BoxOverlay boxes={boxes.filter((b) => b.page === 1)} first={boxes[0] ?? null} />
    </div>
  );
}
