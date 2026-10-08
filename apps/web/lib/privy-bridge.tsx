"use client";

import { PrivyProvider, useLogin, usePrivy } from "@privy-io/react-auth";
import { useState, type ReactNode } from "react";
import type { Source } from "./auth";
import { PRIVY_CONFIG } from "./privy-config";


function Bridge({ render }: { render: (source: Source) => ReactNode }) {
  const { ready, authenticated, getAccessToken, logout } = usePrivy();
  // Privy calls onError on a login error and when the person closes the login window.
  const [loginErrors, setLoginErrors] = useState(0);
  const { login } = useLogin({ onError: () => setLoginErrors((n) => n + 1) });
  return <>{render({ ready, authenticated, getAccessToken, login: () => login(), logout: () => void logout(), loginErrors })}</>;
}

export default function PrivyBridge({ appId, render }: { appId: string; render: (source: Source) => ReactNode }) {
  return (
    <PrivyProvider appId={appId} config={PRIVY_CONFIG}>
      <Bridge render={render} />
    </PrivyProvider>
  );
}
