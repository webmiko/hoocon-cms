import { lazy, type ComponentType, type LazyExoticComponent } from "react";

import {
  clearChunkReloadFlag,
  recoverFromStaleChunk,
} from "./chunkLoadRecovery";

type ModuleDefault<T> = { default: T };

/**
 * ``React.lazy`` that hard-reloads once on stale dynamic-import failures
 * (common right after a deploy while an old SW still serves the shell).
 */
// Props are per-page; match ``React.lazy`` flexibility (not ``unknown`` props).
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- page prop variance
export function lazyWithChunkReload<T extends ComponentType<any>>(
  factory: () => Promise<ModuleDefault<T>>,
): LazyExoticComponent<T> {
  return lazy(() =>
    factory()
      .then((mod) => {
        clearChunkReloadFlag();
        return mod;
      })
      .catch((error: unknown) => {
        if (recoverFromStaleChunk(error)) {
          // Page is reloading; keep Suspense pending.
          return new Promise<ModuleDefault<T>>(() => undefined);
        }
        throw error;
      }),
  );
}
