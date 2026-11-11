import type { ReactNode } from "react";
import "./setup.css";

/**
 * A file picker drawn as a dashed well. The picker's own input lies over the
 * whole well, unseen, so a click anywhere opens it and a file dropped on it
 * lands in it, with no handling of our own. The dashed edge turns solid once
 * a file is chosen, and the well then names it. The words in the well are for
 * the eye; the input keeps its own label and says which file it holds.
 */
export function DropWell({ file, what, children }: { file: File | null; what: string; children: ReactNode }) {
  return (
    <div className={`ft-drop${file ? " has-file" : ""}`}>
      {children}
      <span className="ft-drop__title" aria-hidden="true">
        {file ? file.name : `Drop ${what} here`}
      </span>
      <span className="ft-drop__hint" aria-hidden="true">
        {file ? "Click or drop a file to choose another." : "Or click to choose a file."}
      </span>
    </div>
  );
}
