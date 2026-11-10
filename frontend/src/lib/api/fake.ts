import type { ApiClient } from "./client";
import { chargeFake } from "./fixtures/charge";
import { clockFake } from "./fixtures/clock";
import { closeoutFake } from "./fixtures/closeout";
import { evidenceFake } from "./fixtures/evidence";
import { grantFake } from "./fixtures/grant";
import { mailFake } from "./fixtures/mail";
import { setupFake } from "./fixtures/setup";
import { threadFake } from "./fixtures/thread";

/**
 * The API served from synthetic fixtures, for fake mode (NEXT_PUBLIC_FAKE=1)
 * and tests. Each area's file under fixtures/ serves its own methods, so each
 * screen's builder changes only their file. Every client starts from the
 * sample grant, and what one client writes stays in that client.
 */
export function createFakeApiClient(): ApiClient {
  return {
    ...grantFake(),
    ...clockFake(),
    ...chargeFake(),
    ...threadFake(),
    ...evidenceFake(),
    ...setupFake(),
    ...mailFake(),
    ...closeoutFake(),
  };
}
