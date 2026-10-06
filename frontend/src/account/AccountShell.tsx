/**
 * /account shell — auth-gated layout with section tabs.
 *
 * Anonymous visitors are redirected to /login. Sections map 1:1 to the
 * ``/api/account/*`` resources (ЛК-1..7, 11–13).
 */

import { NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";

import { Seo } from "../components/Seo";
import styles from "./Account.module.css";
import { useAccountAuth } from "./AuthContext";

const SECTIONS: Array<{ to: string; label: string }> = [
  { to: "/account", label: "Сводка" },
  { to: "/account/leads", label: "Заявки" },
  { to: "/account/quotes", label: "КП" },
  { to: "/account/orders", label: "Заказы" },
  { to: "/account/documents", label: "Документы" },
  { to: "/account/specs", label: "Спецификации" },
  { to: "/account/conversations", label: "Диалоги" },
  { to: "/account/rma", label: "Рекламации" },
  { to: "/account/profile", label: "Профиль" },
];

export default function AccountShell() {
  const { session, loading, logout } = useAccountAuth();
  const navigate = useNavigate();

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
        {SECTIONS.map((s) => (
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
