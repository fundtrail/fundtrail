# SignIn

The page before the app: one card with the wordmark, one line on what FundTrail does, one button, and the fine print. The first sign-in then sets up the demo workspace in the same card.

**Use it** as the only page a signed-out user sees. There is no app shell, no navigation and no marketing copy: users sign in with Google, so one button is the whole job.

- **Card:** `ft-si__card`, 420px wide, centered on `paper`, `paper-raised` with a 1px `rule` border and `radius-lg`. Wordmark (20px, 700), then the line from the product docs: "A running evidence file for every research grant, so the review is done before closeout."
- **Button:** our own outlined main button (`ft-btn ft-btn--main ft-si__btn`, 40px tall, full width) that says "Continue with Google". Never draw Google's logo or copy its button styling.
- **Busy:** after the click the button reads "Signing in…" with the working dot and takes the dashed look, using `aria-disabled` so focus stays on it. A visually hidden status says "Signing in with Google."
- **Error:** "Sign-in didn't finish. Try again." in `ft-field__error` above the button (`role="alert"`), and the button works again.
- **Fine print:** "Your first sign-in creates a demo workspace with sample grants. All data in it is synthetic."
- **Setting up (first sign-in only):** the card becomes "Setting up your demo workspace", with four steps: three sample grants, their ledgers (153 charges), their evidence, then opening the workspace. Each step is waiting (dashed ring), copying (the pulsing dot) or done (an ink check). No percentages and no progress bar: the steps are the progress. The fine print names the signed-in address.
- **Opening:** when the copy is done, the last step pulses and the page goes to the workspace home (the Demo hooks `window.FTOpenWorkspace`).
- **Reduced motion:** the dot doesn't pulse, and the steps advance faster.

**Proposal:** copying the seed into a new "Demo workspace" on first sign-in, and showing it as steps, is a proposal. docs/product.md lists how the seed is copied on sign-up as not decided.

**Hash params, for screenshots:** `#state=busy`, `#state=error`, `#state=setup` (with `&step=0` to `2` for the step being copied), `#state=open`, and `&t=dark`.

Don't: add a hero, feature lists or testimonials, show a percentage, or ask for anything before the user has signed in.
