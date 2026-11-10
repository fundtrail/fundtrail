# AgentAnswer

The agent's answer to one question code asked about a charge: the question, the answer, the reasoning and a link to its source, labeled as the agent's.

**The consumer provides** a judgment record: the question, the answer (`supports`, `contradicts` or `unsure`), the reasoning, its citations and the date, plus the author.

- A **supports** answer collapses to one line inside the charge, in an `ft-more ft-more--agent` disclosure: "Agent · Supports · necessary, reasonable and for this project". It opens to the reasoning and the Source link.
- A **contradicts** or **unsure** answer stays open, because the accountant has to act: the question as a `heading`, the answer and date, the reasoning, the Source link.
- The answer word is an `ft-chip`: a colored word in the bucket it leads to (`ft-chip--supports`, `ft-chip--contradicts`, `ft-chip--unsure`).
- The author label is the plain word "Agent" (`ft-tag--agent`), the one label for everything the agent wrote.
- Quotes are not repeated in the charge panel. The Source link opens the viewer at the passage, highlighted there.
- When the accountant has answered, their answer goes on top with "Answered by the accountant, Apr 10, 2026."; the agent's stays below.
- When the agent is answering again, add the Rechecking tag and keep showing the last answer.

Don't: merge the agent's reasoning into code's status text, or drop the label.

Inside a charge's details, an answer is a link in the Trail ("The agent · Supports"); use this layout where answers are reviewed on their own, and in the evidence report.
