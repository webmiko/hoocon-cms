/**
 * /account/orders — order list with progress and shipment tracking (ЛК-6/13).
 */

import { useAsync } from "../hooks/useAsync";
import styles from "./Account.module.css";
import { accountApi } from "./api";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU");
}

export default function OrdersPage() {
  const { data, loading, error } = useAsync(() => accountApi.orders());

  if (loading) return <p className={styles.muted}>Загрузка…</p>;
  if (error) return <p className={styles.error}>Не удалось загрузить заказы.</p>;

  const orders = data ?? [];
  return (
    <section>
      {orders.length === 0 ? (
        <p className={styles.muted}>Заказов пока нет.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Номер</th>
              <th>Статус</th>
              <th>Готовность</th>
              <th>Отгрузка</th>
              <th>ТК / трек</th>
              <th>Дата</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>{o.number}</td>
                <td>
                  <span className={styles.badgeAccent}>{o.status_label}</span>
                </td>
                <td>{o.progress ? `${o.progress}%` : "—"}</td>
                <td>{fmtDate(o.planned_ship_date)}</td>
                <td>
                  {o.carrier_label}
                  {o.track_number ? ` · ${o.track_number}` : ""}
                  {!o.carrier_label && !o.track_number ? "—" : ""}
                </td>
                <td>{fmtDate(o.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
