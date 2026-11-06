export interface SignedInIdentity {
  shown: string;
  full: string;
}

interface AccountIdentity {
  wallet?: { address: string };
  email?: { address: string };
}

/** The wallet comes first, then the email. An account with neither shows nothing. */
export function signedInIdentity(account: AccountIdentity | null): SignedInIdentity | null {
  const wallet = account?.wallet?.address;
  if (wallet) return { shown: `${wallet.slice(0, 6)}…${wallet.slice(-4)}`, full: wallet };
  const email = account?.email?.address;
  return email ? { shown: email, full: email } : null;
}
