/**
 * TEST AUTH FIXTURE. Injected into the page before any app script runs. It hands the app a pre-signed test token.
 * It is not Privy and not part of the product. Production bundles never contain it. The tokens in P03_TOKEN_* are
 * signed with a per-run test key that only the isolated test API trusts.
 */
export async function injectAuth(page, token, label = "TEST AUTH FIXTURE · not Privy · isolated test run") {
  await page.addInitScript(({ token, label }) => {
    window.__EDGE_OS_TEST_AUTH__ = { label, getAccessToken: async () => token, signOut() {} };
  }, { token, label });
}

export const tokens = {
  a: process.env.P03_TOKEN_A,
  b: process.env.P03_TOKEN_B,
  bad: process.env.P03_TOKEN_BAD,
};
