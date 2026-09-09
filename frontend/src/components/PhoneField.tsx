import { useEffect, useRef, useState } from "react";

import {
  digitsOnly,
  formatNational,
  formatPhone,
  guessPhoneCountryFromGeo,
  nationalFromInput,
  parsePhone,
  phoneCountryById,
  PHONE_COUNTRIES,
  type PhoneCountryId,
} from "../utils/phoneMask";
import styles from "./PhoneField.module.css";

type PhoneFieldProps = {
  id: string;
  name?: string;
  value: string;
  onChange: (value: string) => void;
  /** Match parent form input styles (LeadForm `.input`). */
  inputClassName?: string;
  disabled?: boolean;
  required?: boolean;
};

function resolveInitialCountry(value: string): PhoneCountryId {
  if (value.trim()) return parsePhone(value).countryId;
  return guessPhoneCountryFromGeo();
}

/**
 * Phone input with EAEU country dial select and national mask
 * (RU example: ``+7 (999) 999-99-99``).
 * Default country from browser timezone / language (geo heuristic).
 */
export function PhoneField({
  id,
  name = "phone",
  value,
  onChange,
  inputClassName,
  disabled,
  required,
}: PhoneFieldProps) {
  const geoDefault = useRef(guessPhoneCountryFromGeo());
  const userPicked = useRef(false);
  const [countryId, setCountryId] = useState<PhoneCountryId>(() =>
    resolveInitialCountry(value),
  );
  const country = phoneCountryById(countryId);

  // Empty value: restore geo default unless user already chose a country.
  useEffect(() => {
    if (!value.trim()) {
      if (!userPicked.current) {
        setCountryId(geoDefault.current);
      }
      return;
    }
    const parsed = parsePhone(value);
    if (parsed.countryId !== "ru" && parsed.countryId !== "kz") {
      setCountryId(parsed.countryId);
    }
  }, [value]);

  const nationalDigits = (() => {
    const all = digitsOnly(value);
    if (!all) return "";
    if (all.startsWith(country.dial)) {
      return all.slice(country.dial.length).slice(0, country.nationalLength);
    }
    return parsePhone(value).nationalDigits.slice(0, country.nationalLength);
  })();

  const nationalDisplay = formatNational(countryId, nationalDigits);

  function setCountry(nextId: PhoneCountryId) {
    userPicked.current = true;
    setCountryId(nextId);
    const next = phoneCountryById(nextId);
    const national = nationalDigits.slice(0, next.nationalLength);
    onChange(national ? formatPhone(nextId, national) : "");
  }

  function setNational(raw: string) {
    const trimmed = raw.trim();
    if (trimmed.startsWith("+") || /^00\d/.test(trimmed)) {
      const fromPaste = parsePhone(raw);
      userPicked.current = true;
      setCountryId(fromPaste.countryId);
      onChange(
        fromPaste.nationalDigits
          ? formatPhone(fromPaste.countryId, fromPaste.nationalDigits)
          : "",
      );
      return;
    }
    const national = nationalFromInput(countryId, raw);
    onChange(national ? formatPhone(countryId, national) : "");
  }

  const controlClass = [styles.control, inputClassName].filter(Boolean).join(" ");

  return (
    <div className={styles.row}>
      <label className={styles.srOnly} htmlFor={`${id}-country`}>
        Код страны
      </label>
      <select
        id={`${id}-country`}
        className={`${controlClass} ${styles.country}`}
        value={countryId}
        disabled={disabled}
        aria-label="Код страны"
        onChange={(e) => setCountry(e.target.value as PhoneCountryId)}
      >
        {PHONE_COUNTRIES.map((c) => (
          <option key={c.id} value={c.id}>
            {c.label}
          </option>
        ))}
      </select>
      <input
        type="tel"
        id={id}
        name={name}
        autoComplete="tel-national"
        inputMode="numeric"
        disabled={disabled}
        required={required}
        className={controlClass}
        value={nationalDisplay}
        placeholder={country.placeholder}
        onChange={(e) => setNational(e.target.value)}
      />
    </div>
  );
}
