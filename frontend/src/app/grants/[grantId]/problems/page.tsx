import { Suspense } from "react";
import { ProblemsScreen } from "./screen";

// The screen reads the route and its data in the browser, with the signed-in
// user's token, so nothing here is prerendered.
export default function ProblemsPage() {
  return (
    <Suspense fallback={<p className="ft-empty">Loading…</p>}>
      <ProblemsScreen />
    </Suspense>
  );
}
