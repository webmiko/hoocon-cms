/**
 * /account — dashboard counters (ЛК-1).
 */

import { Link } from "react-router-dom";

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi } from "./api";

export default function DashboardPage() {
  const { data, loading } = useAsync(() => accountApi.summary());

  if (loading || !data) {
    return <p className={styles.muted}>Загрузка…</p>;
  }

  const stats: Array<{ label: string; value: number; to: string }> = [
    { label: "Заявок в работе", value: data.active_leads, to: "/account/leads" },
    { label: "КП на рассмотрении", value: data.quotes_pending, to: "/account/quotes" },
    { label: "Заказов в производстве", value: data.orders_in_work, to: "/account/orders" },
    {
      label: "Открытых диалогов",
      value: data.unread_conversations,
      to: "/account/conversations",
    },
  ];

  return (
    <div className={styles.grid}>
      {stats.map((s) => (
        <Link key={s.to} to={s.to} className={styles.card} style={{ textDecoration: "none" }}>
          <p className={styles.statValue}>{s.value}</p>
          <p className={styles.statLabel}>{s.label}</p>
        </Link>
      ))}
    </div>
  );
}
