import { Suspense } from "react";
import { LedgerScreen } from "./screen";

// The screen reads the route and its data in the browser, with the signed-in
// user's token, so nothing here is prerendered.
export default function LedgerPage() {
  return (
    <Suspense fallback={<p className="ft-empty">Loading…</p>}>
      <LedgerScreen />
    </Suspense>
  );
}
