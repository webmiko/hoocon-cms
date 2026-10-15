/**
 * /account shell — auth-gated layout with section tabs.
 *
 * Anonymous visitors are redirected to /login. Sections map 1:1 to the
 * ``/api/account/*`` resources (ЛК-1..7, 11–13).
 */

import { NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";

import { Seo } from "../components/Seo";
import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi, type AccountSummary } from "./api";
import { useAccountAuth } from "./AuthContext";

const CORE_START: Array<{ to: string; label: string }> = [
  { to: "/account", label: "Сводка" },
  { to: "/account/leads", label: "Заявки" },
];

const OPTIONAL: Array<{ to: string; label: string; key: keyof AccountSummary }> = [
  { to: "/account/quotes", label: "КП", key: "quotes_total" },
  { to: "/account/orders", label: "Заказы", key: "orders_total" },
  { to: "/account/documents", label: "Документы", key: "documents_total" },
  { to: "/account/specs", label: "Спецификации", key: "specs_total" },
  { to: "/account/conversations", label: "Диалоги", key: "conversations_total" },
  { to: "/account/rma", label: "Рекламации", key: "rma_total" },
];

const PROFILE = { to: "/account/profile", label: "Профиль" };

export default function AccountShell() {
  const { session, loading, logout } = useAccountAuth();
  const navigate = useNavigate();
  const { data: summary } = useAsync(
    () => (session ? accountApi.summary() : Promise.resolve(null)),
    session?.email ?? "",
  );
  const sections = [
    ...CORE_START,
    ...OPTIONAL.filter((item) => (summary?.[item.key] ?? 0) > 0),
    PROFILE,
  ];

  if (loading) {
    return <div className={styles.page}>Загрузка…</div>;
  }
  if (!session) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className={styles.page}>
      <Seo title="Личный кабинет" description="Личный кабинет клиента Hoocon." noindex />
      <div className={styles.actions} style={{ justifyContent: "space-between" }}>
        <h1 className={styles.title}>Личный кабинет</h1>
        <button
          type="button"
          className={styles.buttonGhost}
          onClick={async () => {
            await logout();
            navigate("/login", { replace: true });
          }}
        >
          Выйти ({session.email})
        </button>
      </div>
      <ul className={styles.tabs}>
        {sections.map((s) => (
          <li key={s.to} className={styles.tab}>
            <NavLink to={s.to} end={s.to === "/account"}>
              {s.label}
            </NavLink>
          </li>
        ))}
      </ul>
      <Outlet />
    </div>
  );
}
