/** Where the app serves PDF.js's WebAssembly decoders, from public/pdfjs/wasm/. */
export const PDF_WASM_PATH = "/pdfjs/wasm/";

/**
 * PDF.js options for every document. `wasmUrl` is where it fetches its
 * WebAssembly image decoders: JBIG2 and JPEG 2000, which scanned PDFs often
 * use. They're copied from the pinned pdfjs-dist by `pnpm pdfjs:wasm` (run
 * before `pnpm dev` and `pnpm build`) and served by the app, never a CDN.
 * One object, so react-pdf doesn't reload the document on each render.
 */
export const PDF_OPTIONS = { wasmUrl: PDF_WASM_PATH } as const;
