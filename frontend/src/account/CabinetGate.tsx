/**
 * CabinetGate — прячет /login, /register и /account/* пока флаг выключен.
 *
 * ``SiteSettings.cabinet_enabled=False`` (Admin → Интеграции) → редирект
 * на главную; API при этом тоже отдаёт 404, так что обхода нет.
 */

import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { AccountAuthProvider } from "./AuthContext";
import { useCabinetEnabled } from "./cabinetEnabled";

interface CabinetGateProps {
  children: ReactNode;
}

export function CabinetGate({ children }: CabinetGateProps) {
  const enabled = useCabinetEnabled();
  if (enabled === null) {
    return null;
  }
  if (!enabled) {
    return <Navigate to="/" replace />;
  }
  // Session probe (/api/csrf + /api/auth/me) only on cabinet routes, not every public page.
  return <AccountAuthProvider>{children}</AccountAuthProvider>;
}
