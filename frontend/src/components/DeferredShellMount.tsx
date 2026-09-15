import { Suspense, type ReactNode } from "react";

import {
  useShellDeferredMount,
  type ShellDeferredMountMode,
} from "../hooks/useShellDeferredMount";

type DeferredShellMountProps = {
  mode: ShellDeferredMountMode;
  children: ReactNode;
  eagerWhen?: () => boolean;
  watchSupportChat?: boolean;
};

/** Lazy shell block: defer mount, then Suspense-load the dynamic chunk. */
export function DeferredShellMount({
  mode,
  children,
  eagerWhen,
  watchSupportChat,
}: DeferredShellMountProps) {
  const ready = useShellDeferredMount({ mode, eagerWhen, watchSupportChat });
  if (!ready) {
    return null;
  }
  return <Suspense fallback={null}>{children}</Suspense>;
}
