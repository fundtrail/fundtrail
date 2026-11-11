import type { ApiClient } from "./client";
import { chargeFake } from "./fixtures/charge";
import { closeoutFake } from "./fixtures/closeout";
import { duplicateFake } from "./fixtures/duplicate";
import { evidenceFake } from "./fixtures/evidence";
import { grantFake, newGrantDetail, sampleSummary } from "./fixtures/grant";
import { mailFake } from "./fixtures/mail";
import { samplesFake } from "./fixtures/samples";
import { setupFake } from "./fixtures/setup";
import { threadFake } from "./fixtures/thread";

/**
 * The API served from synthetic fixtures, for fake mode (NEXT_PUBLIC_FAKE=1)
 * and tests. Each area's file under fixtures/ serves its own methods, so each
 * screen's builder changes only their file. Every client starts from the
 * sample grant, and what one client writes stays in that client.
 */
export function createFakeApiClient(): ApiClient {
  const { addGrant, ...grants } = grantFake();
  const setup = setupFake();
  // The agent's waiting duplicate mark, shared by the evidence card and the charge, settled by a confirmation.
  const duplicate = duplicateFake();
  return {
    ...grants,
    writeRecord: async (grantId, body) => {
      const record = await grants.writeRecord(grantId, body);
      duplicate.wrote(grantId, body);
      return record;
    },
    ...chargeFake(duplicate),
    ...threadFake(),
    ...evidenceFake(duplicate),
    ...setup,
    // A grant added in fake mode is then served like any other, with nothing read yet.
    createGrant: async (workspaceId, awardLetter, fileName) => {
      const grant = await setup.createGrant(workspaceId, awardLetter, fileName);
      addGrant(grant);
      return grant;
    },
    ...mailFake(),
    ...closeoutFake(),
    ...samplesFake({ addGrant, summaryOf: (grant) => newGrantDetail(grant).summary, problemRows: sampleSummary.on_problem_list }),
  };
}
