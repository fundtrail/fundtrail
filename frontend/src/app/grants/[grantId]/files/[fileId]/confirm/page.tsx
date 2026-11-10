import { Suspense } from "react";
import { ConfirmScreen } from "./screen";

// Reads the route, its query and its data in the browser, so nothing here is prerendered.
export default function ConfirmPage() {
  return (
    <Suspense fallback={<p className="ft-empty">Loading…</p>}>
      <ConfirmScreen />
    </Suspense>
  );
}
