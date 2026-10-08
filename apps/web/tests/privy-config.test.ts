import { describe, expect, it } from "vitest";
import { PRIVY_CONFIG } from "../lib/privy-config";

describe("Privy provider configuration (config values only, not Privy behavior)", () => {
  it("creates no wallet at login on any chain", () => {
    expect(PRIVY_CONFIG.embeddedWallets.ethereum.createOnLogin).toBe("off");
    expect(PRIVY_CONFIG.embeddedWallets.solana.createOnLogin).toBe("off");
  });
  it("offers no wallet login method, because a connected wallet is not an identity", () => {
    expect(PRIVY_CONFIG.loginMethods).not.toContain("wallet");
  });
});
