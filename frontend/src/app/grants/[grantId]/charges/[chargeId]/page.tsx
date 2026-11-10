import { Suspense } from "react";
import { ChargeScreen } from "./screen";

// The screen reads the route and its data in the browser, with the signed-in
// user's token, so nothing here is prerendered.
export default function ChargePage() {
  return (
    <Suspense fallback={<p className="ft-empty">Loading…</p>}>
      <ChargeScreen />
    </Suspense>
  );
}
