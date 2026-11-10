"use client";

// Renders a PDF with PDF.js through react-pdf (architecture.md, Stack: "PDF.js
// with a highlight layer"). Only ever loaded in the browser: the viewer
// imports it with next/dynamic and ssr off, because PDF.js needs browser APIs.

import { useState, type ReactNode } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import styles from "./viewer.module.css";

// react-pdf asks for the worker to be set in the module that renders it.
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

export interface PdfPagesProps {
  url: string;
  /** Each page's width in CSS pixels. */
  width: number;
  /** What to draw over a page, such as highlight boxes. */
  overlay: (pageNumber: number) => ReactNode;
  /** The page to scroll to when nothing on it is highlighted. */
  targetPage: number | null;
  /** Called after a page draws, so the viewer can scroll to its target. */
  onPageReady: () => void;
}

export default function PdfPages({ url, width, overlay, targetPage, onPageReady }: PdfPagesProps) {
  const [pages, setPages] = useState(0);
  return (
    <Document
      file={url}
      suspense={false}
      loading={<p className="ft-empty">Loading the file…</p>}
      error={<p className="ft-error">Couldn&apos;t open this PDF.</p>}
      onLoadSuccess={({ numPages }) => setPages(numPages)}
    >
      {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
        <div
          key={n}
          className={styles.pdfPage}
          data-page={n}
          data-scroll-target={n === targetPage ? "true" : undefined}
        >
          <Page
            pageNumber={n}
            width={width}
            suspense={false}
            renderAnnotationLayer={false}
            renderTextLayer={false}
            onRenderSuccess={onPageReady}
          >
            {overlay(n)}
          </Page>
        </div>
      ))}
    </Document>
  );
}
