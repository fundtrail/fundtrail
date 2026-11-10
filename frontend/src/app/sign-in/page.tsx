"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";

/** The only page a signed-out user sees: the wordmark, one line, one button. */
export default function SignIn() {
  const auth = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (auth.state.status === "signed_in") router.replace("/");
  }, [auth.state.status, router]);

  async function signIn() {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      await auth.signIn();
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <div className="ft-si">
      <div className="ft-si__card">
        <div className="ft-wordmark">FundTrail</div>
        <p>A running evidence file for every research grant, so the review is done before closeout.</p>
        {failed && (
          <p className="ft-error" role="alert">
            Sign-in didn&apos;t finish. Try again.
          </p>
        )}
        <button
          type="button"
          className={`ft-btn ft-btn--main ft-si__btn${busy ? " is-busy" : ""}`}
          aria-disabled={busy}
          onClick={() => void signIn()}
        >
          {busy ? "Signing in…" : "Continue with Google"}
        </button>
        {auth.fake && (
          <p className="ft-caption">Fake sign-in: no Supabase project is configured, so this signs in a synthetic demo user.</p>
        )}
      </div>
    </div>
  );
}
