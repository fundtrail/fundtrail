import { Suspense } from "react";
import { FileScreen } from "./screen";

// Reads the route, its query and its data in the browser, so nothing here is prerendered.
export default function FilePage() {
  return (
    <Suspense fallback={<p className="ft-empty">Loading…</p>}>
      <FileScreen />
    </Suspense>
  );
}
