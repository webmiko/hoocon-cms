import { Link } from "react-router-dom";

import styles from "./PdnConsentCheckbox.module.css";

type PdnConsentCheckboxProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
};

/**
 * 152-ФЗ consent for forms that send a name, email or phone. The server
 * rejects the request without ``pdn_consent: true`` and stores when it was given.
 */
export function PdnConsentCheckbox({ checked, onChange, className }: PdnConsentCheckboxProps) {
  return (
    <label className={[styles.consent, className].filter(Boolean).join(" ")}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        Даю согласие на <Link to="/terms">обработку персональных данных</Link> (152-ФЗ).
      </span>
    </label>
  );
}
