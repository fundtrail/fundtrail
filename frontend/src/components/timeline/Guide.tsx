"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { GuideStep, Id, TimelineView } from "@/lib/api";
import { routes } from "@/lib/routes";

/**
 * What happened at each highlight of the larger sample, in plain words, keyed by the
 * highlight's label. A highlight without a sentence shows none.
 */
export const HIGHLIGHT_SAYS: Record<string, string> = {
  "Terms tied to their passages": "Every term of the award is tied to the sentence it came from in the award notice.",
  "Receipt photo you deliver": "Some evidence only exists on paper, like the professor's phone photo of a taxi receipt.",
  "Invoice before its line": "An invoice that arrived before its charge waited, and now links to it on its own.",
  "Shared invoice, 56 of 96": "One kit served two labs. The professor's email gives the split, 56 of 96 samples.",
  "Own fee, own approval": "A professor approving her own conference fee is flagged, not cleared.",
  "Bill under its charge": "The bills linked to this charge add up to sixty dollars less than the charge.",
  "Same invoice twice": "The same invoice came in twice, by email and as a scan. The agent marked the copy.",
  "Held vendor email": "Mail from an address nobody on the grant uses waits, unread, until someone lets it in.",
  "One report, six salary lines": "One effort report clears six months of salary.",
  "Moved off the grant": "A correcting line moves the dinner with wine off the grant.",
  "Over budget": "A field corer takes spending past what's been awarded so far.",
  "More money, a higher limit": "A funding notice arrives; once it's confirmed, the limit rises.",
  "Extension found in Drive": "An extension turns up in Drive; once it's confirmed, every check reruns against the new end date.",
  "Closeout": "The university's 90-day notice: the closeout window opens.",
};

/** The step the highlight waits for, in the guide's words. */
const STEP_WORDS: Record<string, string> = {
  confirm_terms: "confirm the terms",
  deliver_file: "bring the photo in",
  decide_suggestion: "decide whether it's a copy",
  let_in_mail: "let the held email in",
  accept_reason: "accept the problem with a note",
  answer_flag: "answer the agent's question",
  enter_share: "enter the grant's share",
  sign_off: "sign off",
};

const day = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

/** The one button that does the step, or takes the user to it. */
function StepButton({
  grantId,
  workspaceId,
  step,
  className,
  busy,
  onDeliver,
}: {
  grantId: Id;
  workspaceId?: Id;
  step: GuideStep;
  className: string;
  busy: boolean;
  onDeliver: (eventId: Id) => void;
}) {
  switch (step.open) {
    case "terms":
      return <Link className={className} href={routes.terms(grantId)}>Go to Grant terms</Link>;
    case "delivery":
      return (
        <button type="button" className={className} disabled={busy || !step.id} onClick={() => step.id && onDeliver(step.id)}>
          Deliver for me
        </button>
      );
    case "charge":
      return <Link className={className} href={step.id ? routes.charge(grantId, step.id) : routes.charges(grantId)}>{step.action === "accept_reason" ? "Open the problem" : "Open the suggestion"}</Link>;
    case "file":
      return <Link className={className} href={step.id ? routes.file(grantId, step.id) : routes.evidence(grantId)}>{step.action === "accept_reason" ? "Open the problem" : "Open the suggestion"}</Link>;
    case "problems":
      return <Link className={className} href={routes.problemList(grantId)}>Open the problem</Link>;
    case "closeout":
      return <Link className={className} href={routes.closeout(grantId)}>Go to Closeout</Link>;
    case "held_mail":
      return workspaceId ? (
        <Link className={className} href={routes.mail(workspaceId)}>
          Go to Held mail
        </Link>
      ) : null;
  }
}

/**
 * The timeline guide (Alex's ask, "it should guide me"): where the user is among the
 * highlights, what happened there, the step that's theirs, and one main button. The
 * rest of the controls sit under the menu beside it.
 */
export function Guide({
  grantId,
  workspaceId,
  view,
  busy,
  menu,
  onNextHighlight,
  onDeliver,
  onGetFile,
  onCloseoutMove,
}: {
  grantId: Id;
  workspaceId?: Id;
  view: TimelineView;
  busy: boolean;
  menu: ReactNode;
  onNextHighlight: () => void;
  onDeliver: (eventId: Id) => void;
  onGetFile: (eventId: Id) => void;
  onCloseoutMove: (to: string) => void;
}) {
  const total = view.highlight_total ?? 0;
  const index = view.highlight_index ?? 0;
  const label = view.highlight_event?.highlight ?? null;
  const says = label ? HIGHLIGHT_SAYS[label] : undefined;
  const step = view.your_step ?? null;
  const allPlayed = index >= total && !step;
  const reading = view.catching_up;
  const filled = "ft-btn ft-btn--sm ft-btn--main";
  const outlined = "ft-btn ft-btn--sm";

  let nextNote: string | null = null;
  if (step) nextNote = "Do your step first";
  else if (reading) nextNote = "The agent is still reading what arrived.";
  else if (view.next_highlight_unavailable_reason) nextNote = view.next_highlight_unavailable_reason;

  return (
    <div className="ft-guide">
      <div className="ft-guide__where">
        <span className="ft-guide__chip">
          Highlight {index} of {total}
        </span>
        {label && <span className="ft-strong ft-guide__label">{label}</span>}
        <span className="ft-num ft-guide__date">{day(view.now.now)}</span>
        {menu}
      </div>
      <div className="ft-guide__bar" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={i < index ? "ft-guide__seg ft-guide__seg--done" : "ft-guide__seg"} />
        ))}
      </div>
      {says && <p className="ft-guide__says">{says}</p>}
      {allPlayed ? (
        <div className="ft-guide__step">
          <p>
            Every highlight is played.
            {view.sign_off_at ? ` To close out, move to ${day(view.sign_off_at)} and sign off.` : " To close out, sign off on Closeout."}
          </p>
          <span className="ft-guide__actions">
            {view.sign_off_at && Date.parse(view.now.now) < Date.parse(view.sign_off_at) && (
              <button type="button" className={filled} disabled={busy} onClick={() => onCloseoutMove(view.sign_off_at!)}>
                Move to {day(view.sign_off_at)}
              </button>
            )}
            <Link className={view.sign_off_at && Date.parse(view.now.now) < Date.parse(view.sign_off_at) ? outlined : filled} href={routes.closeout(grantId)}>
              Go to Closeout
            </Link>
          </span>
        </div>
      ) : (
        <div className="ft-guide__step">
          {step ? (
            <p>
              <span className="ft-strong">Your step:</span> {STEP_WORDS[step.action] ?? "make this highlight's step"}.
            </p>
          ) : (
            <p>Nothing for you to do here.</p>
          )}
          <span className="ft-guide__actions">
            {step ? (
              <>
                <StepButton grantId={grantId} workspaceId={workspaceId} step={step} className={filled} busy={busy} onDeliver={onDeliver} />
                {step.open === "delivery" && step.id && (
                  <button type="button" className={outlined} disabled={busy} onClick={() => onGetFile(step.id!)}>
                    Get the file
                  </button>
                )}
              </>
            ) : (
              <>
                {view.highlight_event?.charge_id && (
                  <Link className={outlined} href={routes.charge(grantId, view.highlight_event.charge_id)}>
                    Open the charge
                  </Link>
                )}
                {!view.highlight_event?.charge_id && view.highlight_event?.file_id && (
                  <Link className={outlined} href={routes.file(grantId, view.highlight_event.file_id)}>
                    Open the file
                  </Link>
                )}
              </>
            )}
            <span className="ft-guide__next">
              <button
                type="button"
                className={step || reading ? outlined : filled}
                disabled={busy || !!nextNote}
                onClick={onNextHighlight}
              >
                Next highlight
              </button>
              {nextNote && <span className="ft-caption">{nextNote}</span>}
            </span>
          </span>
        </div>
      )}
    </div>
  );
}
