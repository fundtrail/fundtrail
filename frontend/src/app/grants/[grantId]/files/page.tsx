import { Suspense } from "react";
import { EvidenceScreen } from "./screen";

// The screen reads its data in the browser with the signed-in user's token, so
// nothing here is prerendered.
export default function EvidencePage() {
  return (
    <Suspense fallback={<p className="ft-empty">Loading…</p>}>
      <EvidenceScreen />
    </Suspense>
  );
}
