// @vitest-environment node
import { execSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import pkg from "../../../package.json";
import { PDF_OPTIONS, PDF_WASM_PATH } from "./pdfOptions";

describe("PDF.js decoders for scanned PDFs", () => {
  it("are served by the app, not a CDN", () => {
    expect(PDF_OPTIONS.wasmUrl).toBe(PDF_WASM_PATH);
    expect(PDF_WASM_PATH).toMatch(/^\/[^/]/);
    expect(PDF_WASM_PATH.endsWith("/")).toBe(true);
  });

  it("are copied from the pinned pdfjs-dist before dev and build", () => {
    expect(pkg.scripts.dev.startsWith("pnpm pdfjs:wasm && ")).toBe(true);
    expect(pkg.scripts.build.startsWith("pnpm pdfjs:wasm && ")).toBe(true);
    expect(pkg.dependencies["pdfjs-dist"]).toBe(JSON.parse(readFileSync("node_modules/react-pdf/package.json", "utf8")).dependencies["pdfjs-dist"]);
  });

  it("include the JBIG2 and JPEG 2000 decoders once copied", () => {
    // Runs the same copy into a temporary folder, from the frontend folder the tests run in.
    const out = mkdtempSync(join(tmpdir(), "pdfjs-wasm-"));
    try {
      execSync(pkg.scripts["pdfjs:wasm"].replace("'public/pdfjs/wasm'", JSON.stringify(join(out, "wasm")).replaceAll('"', "'")));
      for (const f of ["jbig2.wasm", "openjpeg.wasm", "LICENSE_JBIG2", "LICENSE_OPENJPEG"]) expect(existsSync(join(out, "wasm", f))).toBe(true);
      expect(existsSync(join(out, "wasm", "quickjs-eval.wasm"))).toBe(false);
    } finally {
      rmSync(out, { recursive: true, force: true });
    }
  });
});
