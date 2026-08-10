import { useEffect, useState } from "react";

import styles from "./LeadForm.module.css";
import {
  appendBallValveKitToMessage,
  defaultBallValveKitSelection,
  formatDriveCode,
  resolveBracketForDrive,
  type BallValveKitOptions,
  type BallValveKitSelection,
} from "../utils/ballValveKit";

type BallValveKitFieldsProps = {
  kit: BallValveKitOptions;
  baseMessage: string;
  onMessageChange: (message: string) => void;
};

export function BallValveKitFields({
  kit,
  baseMessage,
  onMessageChange,
}: BallValveKitFieldsProps) {
  const [selection, setSelection] = useState<BallValveKitSelection>(() =>
    defaultBallValveKitSelection(kit),
  );

  useEffect(() => {
    onMessageChange(appendBallValveKitToMessage(baseMessage, selection));
  }, [baseMessage, onMessageChange, selection]);

  function updateSelection(patch: Partial<BallValveKitSelection>) {
    setSelection((prev) => {
      const next = { ...prev, ...patch };
      if (patch.driveFamily !== undefined) {
        next.bracket = resolveBracketForDrive(kit, next.driveFamily);
      }
      if (patch.includeActuator === true && !prev.includeActuator) {
        next.includeBracket = true;
      }
      if (patch.includeActuator === false) {
        next.includeBracket = false;
      }
      return next;
    });
  }

  const drivePreview = selection.driveFamily
    ? formatDriveCode(selection.driveFamily, selection.suffix)
    : "";

  return (
    <fieldset className={styles.kitFieldset}>
      <legend className={styles.kitLegend}>Дополнительно к крану</legend>
      <label className={styles.kitCheck}>
        <input
          type="checkbox"
          checked={selection.includeActuator}
          onChange={(event) =>
            updateSelection({ includeActuator: event.target.checked })
          }
        />
        <span>Добавить электропривод</span>
      </label>

      {selection.includeActuator ? (
        <div className={styles.kitGrid}>
          <div className={styles.field}>
            <label htmlFor="bv-drive-family" className={styles.label}>
              Серия привода
            </label>
            <select
              id="bv-drive-family"
              className={styles.input}
              value={selection.driveFamily}
              onChange={(event) =>
                updateSelection({ driveFamily: event.target.value })
              }
            >
              {kit.drive_families.map((family) => (
                <option key={family} value={family}>
                  {family}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.field}>
            <label htmlFor="bv-drive-suffix" className={styles.label}>
              Исполнение
            </label>
            <select
              id="bv-drive-suffix"
              className={styles.input}
              value={selection.suffix}
              onChange={(event) => updateSelection({ suffix: event.target.value })}
            >
              {kit.suffixes.map((suffix) => (
                <option key={suffix} value={suffix}>
                  {suffix}
                </option>
              ))}
            </select>
          </div>

          <p className={styles.kitHint}>
            Артикул привода: <strong>{drivePreview}</strong>
          </p>

          <label className={styles.kitCheck}>
            <input
              type="checkbox"
              checked={selection.includeBracket}
              onChange={(event) =>
                updateSelection({ includeBracket: event.target.checked })
              }
            />
            <span>С кронштейном</span>
          </label>

          {selection.includeBracket ? (
            <p className={styles.kitHint}>
              Кронштейн: <strong>{selection.bracket}</strong>
              {selection.bracket === "BR-ML" ? " (для серии DA5FU)" : ""}
            </p>
          ) : null}
        </div>
      ) : (
        <p className={styles.kitHint}>
          Совместимые серии: {kit.drive_families.join(", ")}. Кронштейны:{" "}
          {kit.bracket_hint}.
        </p>
      )}
    </fieldset>
  );
}
