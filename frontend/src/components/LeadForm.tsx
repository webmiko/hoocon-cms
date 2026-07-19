import { useState } from "react";

import { api, ApiError } from "../api/client";
import styles from "./LeadForm.module.css";

/**
 * Lead form for RFQ / consultation / replacement requests.
 *
 * Spec: ПЛАН §6 Iter 3–4; docs/security-baseline.md §3.
 * - Honeypot field `website` (hidden from real users; bots fill it).
 * - PII (email/phone) sent to backend; backend never returns them.
 * - On success: show confirmation message.
 * - On error: show validation errors.
 */

type LeadType = "rfq" | "consultation" | "replacement";

interface LeadFormProps {
  leadType: LeadType;
  skuSlug?: string;
  skuName?: string;
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

export function LeadForm({ leadType, skuSlug, skuName }: LeadFormProps) {
  const [form, setForm] = useState<FormState>(INITIAL_STATE);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setErrors({});

    const payload: Record<string, unknown> = {
      lead_type: leadType,
      name: form.name,
      email: form.email,
      phone: form.phone,
      company: form.company,
      message: form.message,
      website: form.website, // honeypot
    };

    if (leadType === "rfq" && form.quantity) {
      payload.quantity = parseInt(form.quantity, 10);
    }
    if (leadType === "replacement" && form.analog_belimo_code) {
      payload.analog_belimo_code = form.analog_belimo_code;
    }
    if (skuSlug) {
      // The backend resolves sku by slug; we pass it for context.
      payload.sku = skuSlug;
    }

    try {
      await api.createLead(payload);
      setSuccess(true);
      setForm(INITIAL_STATE);
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
        <h3>Заявка отправлена!</h3>
        <p>Менеджер свяжется с вами в ближайшее время.</p>
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

  const defaultMessage = skuName
    ? `Прошу подготовить КП на ${skuName}.`
    : "";

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      {/* Honeypot — hidden from real users via CSS */}
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

      <div className={styles.field}>
        <label htmlFor="name" className={styles.label}>
          Имя *
        </label>
        <input
          type="text"
          id="name"
          name="name"
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
          required
          value={form.email}
          onChange={(e) => update("email", e.target.value)}
          className={styles.input}
        />
        {errors.email && <span className={styles.error}>{errors.email}</span>}
      </div>

      <div className={styles.fieldRow}>
        <div className={styles.field}>
          <label htmlFor="phone" className={styles.label}>
            Телефон
          </label>
          <input
            type="tel"
            id="phone"
            name="phone"
            value={form.phone}
            onChange={(e) => update("phone", e.target.value)}
            className={styles.input}
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="company" className={styles.label}>
            Компания
          </label>
          <input
            type="text"
            id="company"
            name="company"
            value={form.company}
            onChange={(e) => update("company", e.target.value)}
            className={styles.input}
          />
        </div>
      </div>

      {leadType === "rfq" && (
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
      )}

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

      <div className={styles.field}>
        <label htmlFor="message" className={styles.label}>
          Сообщение *
        </label>
        <textarea
          id="message"
          name="message"
          required
          rows={4}
          value={form.message || defaultMessage}
          onChange={(e) => update("message", e.target.value)}
          className={styles.textarea}
        />
        {errors.message && <span className={styles.error}>{errors.message}</span>}
      </div>

      {errors.detail && <div className={styles.errorBox}>{errors.detail}</div>}

      <button type="submit" className={styles.submitButton} disabled={submitting}>
        {submitting ? "Отправка…" : "Отправить заявку"}
      </button>

      <p className={styles.privacy}>
        Нажимая «Отправить», вы соглашаетесь на обработку персональных данных
        для связи с вами по заявке.
      </p>
    </form>
  );
}
