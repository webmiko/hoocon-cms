import { drfFieldErrors, httpStatusMessage } from "../utils/drfErrors";

/** Fields LeadForm renders inline; any other server error goes to the box. */
const INLINE_FIELDS = new Set(["items", "name", "email", "company", "message", "pdn"]);
/** Server field name → LeadForm error slot. */
const FIELD_ALIASES: Record<string, string> = { pdn_consent: "pdn" };

/**
 * DRF 400 body → LeadForm errors. Unknown fields (phone, quantity, sku,
 * non_field_errors) and nested items[i].quantity used to vanish or show
 * «[object Object]»; they now land in ``detail`` next to the submit button.
 */
export function leadFormErrors(status: number, body: unknown): Record<string, string> {
  const errors: Record<string, string> = {};
  const extra: string[] = [];
  for (const [rawKey, msg] of Object.entries(drfFieldErrors(body))) {
    const key = FIELD_ALIASES[rawKey] ?? rawKey;
    if (INLINE_FIELDS.has(key)) errors[key] = msg;
    else if (!extra.includes(msg)) extra.push(msg);
  }
  if (extra.length > 0) errors.detail = extra.join(" ");
  if (Object.keys(errors).length === 0) errors.detail = httpStatusMessage(status);
  return errors;
}
