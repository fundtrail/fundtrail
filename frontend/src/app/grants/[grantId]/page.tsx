import { Suspense } from "react";
import { GrantScreen } from "./screen";

// The screen reads the route and its data in the browser, with the signed-in
// user's token, so nothing here is prerendered.
export default function GrantPage() {
  return (
    <Suspense fallback={<p className="ft-empty">Loading…</p>}>
      <GrantScreen />
    </Suspense>
  );
}
