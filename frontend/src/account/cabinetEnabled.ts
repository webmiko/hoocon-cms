/**
 * Cabinet feature flag — ``GET /api/settings/public/`` → ``cabinet_enabled``.
 *
 * Пока флаг выключен в Admin → Интеграции, кабинет «не подхватывается»:
 * API отдаёт 404, оффер после заявки скрыт, /account-роуты ведут на главную.
 * Fetch кэшируется на уровне модуля — один запрос на сессию SPA.
 */

import { useEffect, useState } from "react";

let cached: Promise<boolean> | null = null;

/** Загрузить флаг один раз; сбой сети трактуем как «выключено». */
export function fetchCabinetEnabled(): Promise<boolean> {
  if (!cached) {
    cached = fetch("/api/settings/public/")
      .then((response) => (response.ok ? response.json() : {}))
      .then((data: { cabinet_enabled?: boolean }) => data?.cabinet_enabled === true)
      .catch(() => false);
  }
  return cached;
}

/**
 * React-хук: ``null`` пока флаг грузится, затем ``true``/``false``.
 */
export function useCabinetEnabled(): boolean | null {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    void fetchCabinetEnabled().then((value) => {
      if (alive) {
        setEnabled(value);
      }
    });
    return () => {
      alive = false;
    };
  }, []);
  return enabled;
}
