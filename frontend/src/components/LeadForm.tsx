import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { useCompare } from "../compare/useCompare";
import { BallValveKitFields } from "./BallValveKitFields";
import type { BallValveKitOptions } from "../utils/ballValveKit";
import { trackLeadSubmit } from "../utils/analyticsTrack";
import styles from "./LeadForm.module.css";

/**
 * Lead form for RFQ / consultation / replacement requests.
 *
 * Spec: ПЛАН §6 Iter 3–4; docs/security-baseline.md §3.
 * RFQ: company required; multi-SKU via ``items``; soft-bundle hint.
 */

type LeadType = "rfq" | "consultation" | "replacement";

interface LeadFormProps {
  leadType: LeadType;
  skuSlug?: string;
  skuName?: string;
  /** Prefill RFQ line items (compare / ?skus= — prefer slugs). */
  skuCodes?: string[];
  ballValveKit?: BallValveKitOptions | null;
  /** Denser PDP embed: tighter gaps, no multi-КП hint. */
  compact?: boolean;
}

interface FormState {
  name: string;
  email: string;
  phone: string;
  company: string;
  message: string;
  quantity: string;
  analog_belimo_code: string;
  website: string; // honeypot
}

interface LineItem {
  /** Catalog slug when known; otherwise treated as sku_code. */
  key: string;
  /** Human label (sku_code); falls back to key until resolved. */
  label: string;
  name: string;
  quantity: string;
}

const INITIAL_STATE: FormState = {
  name: "",
  email: "",
  phone: "",
  company: "",
  message: "",
  quantity: "",
  analog_belimo_code: "",
  website: "",
};

const BUNDLE_HINT =
  "Заявки с одной компанией и одним именем менеджер обработает как одно КП. "
  + "Нужны разные КП — укажите разные компании.";

function buildDefaultMessage(skuCodes?: string[], skuName?: string): string {
  const codes = (skuCodes ?? []).map((c) => c.trim()).filter(Boolean);
  if (codes.length > 1) {
    return "Прошу подготовить КП по списку артикулов в заявке.";
  }
  if (codes.length === 1) {
    return `Прошу подготовить КП на ${codes[0]}.`;
  }
  if (skuName) {
    return `Прошу подготовить КП на ${skuName}.`;
  }
  return "";
}

function initialLines(
  skuSlug?: string,
  skuCodes?: string[],
  skuName?: string,
): LineItem[] {
  const codes = (skuCodes ?? []).map((c) => c.trim()).filter(Boolean);
  if (codes.length > 0) {
    return codes.map((key) => ({
      key,
      label: key,
      name: "",
      quantity: "1",
    }));
  }
  if (skuSlug) {
    return [
      {
        key: skuSlug,
        label: skuName || skuSlug,
        name: skuName || "",
        quantity: "1",
      },
    ];
  }
  return [];
}

function looksLikeSlug(value: string): boolean {
  return /^[a-z0-9]+(?:-[a-z0-9]+)+$/.test(value);
}

export function LeadForm({
  leadType,
  skuSlug,
  skuName,
  skuCodes,
  ballValveKit,
  compact = false,
}: LeadFormProps) {
  const { items: compareItems } = useCompare();
  const defaultMessage = useMemo(
    () => buildDefaultMessage(skuCodes, skuName),
    [skuCodes, skuName],
  );
  const [form, setForm] = useState<FormState>(() => ({
    ...INITIAL_STATE,
    message: buildDefaultMessage(skuCodes, skuName),
  }));
  const [lines, setLines] = useState<LineItem[]>(() =>
    initialLines(skuSlug, skuCodes, skuName),
  );
  const [pdnConsent, setPdnConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // CSRF only when the form is mounted — not on every page (home Lighthouse).
  useEffect(() => {
    void api.fetchCsrfToken().catch((err) => {
      console.warn("CSRF token fetch failed:", err);
    });
  }, []);

  const lineKeys = (skuCodes ?? []).join(",") || skuSlug || "";
  const compareSig = compareItems
    .map((row) => `${row.slug}:${row.sku_code}`)
    .join("|");

  // Resolve slug → sku_code / name for readable RFQ lines.
  useEffect(() => {
    if (leadType !== "rfq") {
      return;
    }
    const base = initialLines(skuSlug, skuCodes, skuName);
    if (base.length === 0) {
      return;
    }
    const bySlug = new Map(
      compareItems.map((row) => [row.slug, row] as const),
    );
    const fromCompare = base.map((line) => {
      const hit = bySlug.get(line.key);
      if (!hit) return line;
      return {
        ...line,
        label: hit.sku_code || line.label,
        name: hit.name || line.name,
      };
    });
    const needsApi = fromCompare.some(
      (line) => line.label === line.key && looksLikeSlug(line.key),
    );
    let cancelled = false;
    if (!needsApi) {
      // Defer setState out of the effect body (react-hooks/set-state-in-effect).
      const frame = window.requestAnimationFrame(() => {
        if (!cancelled) setLines((prev) => mergeQty(prev, fromCompare));
      });
      return () => {
        cancelled = true;
        window.cancelAnimationFrame(frame);
      };
    }
    const slugs = fromCompare.map((line) => line.key).filter(looksLikeSlug);
    void api
      .compare(slugs)
      .then((data) => {
        if (cancelled) return;
        const map = new Map(data.skus.map((sku) => [sku.slug, sku]));
        const resolved = fromCompare.map((line) => {
          const sku = map.get(line.key);
          if (!sku) return line;
          return {
            ...line,
            label: sku.sku_code || line.label,
            name: sku.name || line.name,
          };
        });
        setLines((prev) => mergeQty(prev, resolved));
      })
      .catch(() => {
        if (!cancelled) setLines((prev) => mergeQty(prev, fromCompare));
      });
    return () => {
      cancelled = true;
    };
    // Intentional: resolve when selection keys / compare labels change.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fingerprint deps
  }, [leadType, lineKeys, skuName, compareSig]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleKitMessage(message: string) {
    setForm((prev) => ({ ...prev, message }));
  }

  function updateLineQty(index: number, quantity: string) {
    setLines((prev) =>
      prev.map((line, i) => (i === index ? { ...line, quantity } : line)),
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pdnConsent) {
      setErrors({
        pdn: "Отметьте согласие на обработку персональных данных",
      });
      return;
    }
    if (leadType === "rfq" && !form.company.trim()) {
      setErrors({ company: "Для запроса КП укажите компанию." });
      return;
    }
    setSubmitting(true);
    setErrors({});

    const message = (form.message || defaultMessage).trim();
    const payload: Record<string, unknown> = {
      lead_type: leadType,
      name: form.name,
      email: form.email,
      phone: form.phone,
      company: form.company.trim(),
      message: message || "Прошу подготовить коммерческое предложение.",
      website: form.website, // honeypot
    };

    if (leadType === "replacement" && form.analog_belimo_code) {
      payload.analog_belimo_code = form.analog_belimo_code;
    }

    if (leadType === "rfq" && lines.length > 0) {
      payload.items = lines.map((line) => {
        const qty = parseInt(line.quantity, 10);
        const item: Record<string, unknown> = {
          quantity: Number.isFinite(qty) && qty > 0 ? qty : 1,
        };
        if (skuSlug && line.key === skuSlug) {
          item.sku = line.key;
        } else if (looksLikeSlug(line.key)) {
          item.sku = line.key;
        } else {
          item.sku_code = line.key;
        }
        return item;
      });
    } else if (skuSlug) {
      payload.sku = skuSlug;
      if (form.quantity) {
        payload.quantity = parseInt(form.quantity, 10);
      }
    } else if (leadType === "rfq" && form.quantity) {
      payload.quantity = parseInt(form.quantity, 10);
    }

    try {
      await api.createLead(payload);
      trackLeadSubmit(leadType);
      setSuccess(true);
      setForm(INITIAL_STATE);
      setLines(initialLines(skuSlug, skuCodes, skuName));
      setPdnConsent(false);
    } catch (err) {
      if (err instanceof ApiError) {
        const fieldErrors: Record<string, string> = {};
        for (const [key, value] of Object.entries(err.body)) {
          if (Array.isArray(value) && value.length > 0) {
            fieldErrors[key] = String(value[0]);
          } else if (typeof value === "string") {
            fieldErrors[key] = value;
          }
        }
        setErrors(fieldErrors);
      } else {
        setErrors({ message: "Произошла ошибка. Попробуйте позже." });
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <div className={styles.success}>
        <h3>Заявка отправлена</h3>
        <p>
          Ответим до 2 рабочих часов — на email или телефон из заявки. Если нужны
          уточнения по характеристикам или объёму, напишем в том же ответе.
        </p>
        <button
          type="button"
          className={styles.resetButton}
          onClick={() => setSuccess(false)}
        >
          Отправить ещё одну заявку
        </button>
      </div>
    );
  }

  const messageValue = form.message || defaultMessage;
  const showBallValveKit = leadType === "rfq" && ballValveKit;
  const showLines = leadType === "rfq" && lines.length > 0;

  return (
    <form
      className={compact ? `${styles.form} ${styles.formCompact}` : styles.form}
      onSubmit={handleSubmit}
    >
      <div className={styles.honeypot} aria-hidden="true">
        <label htmlFor="website">Website (leave empty)</label>
        <input
          type="text"
          id="website"
          name="website"
          value={form.website}
          onChange={(e) => update("website", e.target.value)}
          tabIndex={-1}
          autoComplete="off"
        />
      </div>

      {leadType === "rfq" && !compact ? (
        <p className={styles.bundleHint}>{BUNDLE_HINT}</p>
      ) : null}

      {showLines ? (
        <div className={styles.field}>
          <span className={styles.label}>Позиции для КП</span>
          <ul className={styles.lines}>
            {lines.map((line, index) => (
              <li key={`${line.key}-${index}`} className={styles.lineRow}>
                <span className={styles.lineMeta}>
                  <span className={styles.lineCode}>{line.label}</span>
                  {line.name && line.name !== line.label ? (
                    <span className={styles.lineName}>{line.name}</span>
                  ) : null}
                </span>
                <label className={styles.lineQty}>
                  <span className={styles.lineQtyLabel}>кол-во</span>
                  <input
                    type="number"
                    min={1}
                    value={line.quantity}
                    onChange={(e) => updateLineQty(index, e.target.value)}
                    className={styles.input}
                  />
                </label>
              </li>
            ))}
          </ul>
          {errors.items ? (
            <span className={styles.error}>{errors.items}</span>
          ) : null}
        </div>
      ) : null}

      <div className={styles.fieldsGrid}>
        <div className={styles.field}>
          <label htmlFor="name" className={styles.label}>
            Имя *
          </label>
          <input
            type="text"
            id="name"
            name="name"
            autoComplete="name"
            required
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            className={styles.input}
          />
          {errors.name && <span className={styles.error}>{errors.name}</span>}
        </div>

        <div className={styles.field}>
          <label htmlFor="email" className={styles.label}>
            Email *
          </label>
          <input
            type="email"
            id="email"
            name="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={(e) => update("email", e.target.value)}
            className={styles.input}
          />
          {errors.email && <span className={styles.error}>{errors.email}</span>}
        </div>

        <div className={styles.field}>
          <label htmlFor="phone" className={styles.label}>
            Телефон
          </label>
          <input
            type="tel"
            id="phone"
            name="phone"
            autoComplete="tel"
            value={form.phone}
            onChange={(e) => update("phone", e.target.value)}
            className={styles.input}
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="company" className={styles.label}>
            Компания{leadType === "rfq" ? " *" : ""}
          </label>
          <input
            type="text"
            id="company"
            name="company"
            required={leadType === "rfq"}
            autoComplete="organization"
            value={form.company}
            onChange={(e) => update("company", e.target.value)}
            className={styles.input}
          />
          {errors.company ? (
            <span className={styles.error}>{errors.company}</span>
          ) : null}
        </div>
      </div>

      {leadType === "rfq" && !showLines ? (
        <div className={styles.field}>
          <label htmlFor="quantity" className={styles.label}>
            Количество
          </label>
          <input
            type="number"
            id="quantity"
            name="quantity"
            min="1"
            value={form.quantity}
            onChange={(e) => update("quantity", e.target.value)}
            className={styles.input}
          />
        </div>
      ) : null}

      {leadType === "replacement" && (
        <div className={styles.field}>
          <label htmlFor="analog_belimo_code" className={styles.label}>
            Код аналога Belimo
          </label>
          <input
            type="text"
            id="analog_belimo_code"
            name="analog_belimo_code"
            value={form.analog_belimo_code}
            onChange={(e) => update("analog_belimo_code", e.target.value)}
            className={styles.input}
            placeholder="напр. LM24A-SR"
          />
        </div>
      )}

      {showBallValveKit ? (
        <BallValveKitFields
          kit={ballValveKit}
          baseMessage={defaultMessage}
          onMessageChange={handleKitMessage}
        />
      ) : null}

      <div className={styles.field}>
        <label htmlFor="message" className={styles.label}>
          Сообщение *
        </label>
        <textarea
          id="message"
          name="message"
          required
          rows={compact ? 3 : 4}
          value={messageValue}
          onChange={(e) => update("message", e.target.value)}
          className={styles.textarea}
        />
        {errors.message && <span className={styles.error}>{errors.message}</span>}
      </div>

      {errors.detail && <div className={styles.errorBox}>{errors.detail}</div>}

      <label className={styles.consent}>
        <input
          type="checkbox"
          checked={pdnConsent}
          onChange={(event) => {
            setPdnConsent(event.target.checked);
            if (errors.pdn) {
              setErrors((prev) => {
                const next = { ...prev };
                delete next.pdn;
                return next;
              });
            }
          }}
        />
        <span>
          Даю отдельное{" "}
          <Link to="/terms">согласие на обработку персональных данных</Link>
          {" "}
          (152-ФЗ). Cookie настраиваются отдельно в баннере или в подвале сайта.
        </span>
      </label>
      {errors.pdn ? <span className={styles.error}>{errors.pdn}</span> : null}

      <button
        type="submit"
        className={styles.submitButton}
        disabled={submitting || !pdnConsent}
      >
        {submitting ? "Отправка…" : "Отправить заявку"}
      </button>

      <p className={styles.privacy}>
        Условия поставки —{" "}
        <Link to="/oferta">публичная оферта</Link>. Политика обработки ПДн —{" "}
        <Link to="/privacy-policy">на сайте</Link>.
      </p>
    </form>
  );
}

/** Keep user-edited quantities when labels refresh. */
function mergeQty(prev: LineItem[], next: LineItem[]): LineItem[] {
  const qtyByKey = new Map(prev.map((row) => [row.key, row.quantity]));
  return next.map((row) => ({
    ...row,
    quantity: qtyByKey.get(row.key) ?? row.quantity,
  }));
}
