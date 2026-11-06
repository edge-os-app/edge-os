"use client";

import { PrivyProvider, useCreateWallet, useLogin, usePrivy } from "@privy-io/react-auth";
import { useCallback, useState, type ReactNode } from "react";
import type { Source } from "./auth";
import type { CreatedWallet } from "./wallet-setup-api";
import { PRIVY_CONFIG } from "./privy-config";


function Bridge({ render }: { render: (source: Source) => ReactNode }) {
  const { ready, authenticated, getAccessToken, logout } = usePrivy();
  // Privy calls onError on a login error and when the person closes the login window.
  const [loginErrors, setLoginErrors] = useState(0);
  const { login } = useLogin({ onError: () => setLoginErrors((n) => n + 1) });
  const { createWallet } = useCreateWallet();
  // One additional embedded Ethereum wallet. The caller asks only after the server permits it.
  const createEmbeddedWallet = useCallback(async (): Promise<CreatedWallet> => {
    const wallet = await createWallet({ createAdditional: true });
    return { id: wallet.id ?? null, address: wallet.address, chainType: wallet.chainType, walletIndex: wallet.walletIndex ?? null };
  }, [createWallet]);
  return <>{render({ ready, authenticated, getAccessToken, login: () => login(), logout: () => void logout(), loginErrors, createEmbeddedWallet })}</>;
}

export default function PrivyBridge({ appId, render }: { appId: string; render: (source: Source) => ReactNode }) {
  return (
    <PrivyProvider appId={appId} config={PRIVY_CONFIG}>
      <Bridge render={render} />
    </PrivyProvider>
  );
}
