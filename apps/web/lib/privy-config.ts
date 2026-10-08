/** Privy provider settings. Login creates no wallet (P01 D11). Checked by a test, not by Privy. */
export const PRIVY_CONFIG = {
  embeddedWallets: {
    ethereum: { createOnLogin: "off" as const },
    solana: { createOnLogin: "off" as const },
  },
  // Login methods follow the builder's open question Q5. A connected wallet is not an identity, so it is excluded.
  loginMethods: ["email"] as ("email")[],
};
