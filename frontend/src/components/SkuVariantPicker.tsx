import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  applyVariantPatch,
  selectionFromSibling,
  type SiblingEdition,
  type VariantSelection,
} from "../utils/skuVariantResolve";
import { catalogSkuPath } from "../utils/catalogPaths";
import styles from "./SkuVariantPicker.module.css";

type Props = {
  siblings: SiblingEdition[];
  currentSlug: string;
  categorySlug: string;
  /** Called with the resolved sibling slug before soft navigation. */
  onEditionChange?: (slug: string) => void;
};

function AxisSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (next: string) => void;
}) {
  if (options.length <= 1) return null;
  const safeValue = options.includes(value) ? value : options[0];
  return (
    <label className={styles.axis}>
      <span className={styles.axisLabel}>{label}</span>
      <select
        className={styles.select}
        value={safeValue}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Multi-axis edition picker for family Products (H81 kits / brass / LAV).
 * Navigates to the matching sibling SKU URL when the selection resolves.
 */
export function SkuVariantPicker({
  siblings,
  currentSlug,
  categorySlug,
  onEditionChange,
}: Props) {
  const navigate = useNavigate();
  const current = useMemo(
    () => siblings.find((row) => row.slug === currentSlug) ?? siblings[0],
    [siblings, currentSlug],
  );
  const [selection, setSelection] = useState<VariantSelection>(() =>
    selectionFromSibling(current),
  );
  const [selectionSlug, setSelectionSlug] = useState(current.slug);

  // Keep local selection aligned when the route SKU changes.
  if (selectionSlug !== current.slug) {
    setSelectionSlug(current.slug);
    setSelection(selectionFromSibling(current));
  }

  const waysOpts = useMemo(
    () => [...new Set(siblings.map((s) => s.ways).filter(Boolean))],
    [siblings],
  );
  const dnOpts = useMemo(() => {
    const set = new Set<string>();
    for (const row of siblings) {
      if (selection.ways && row.ways !== selection.ways) continue;
      if (row.dn) set.add(row.dn);
    }
    return [...set].sort((a, b) => Number(a) - Number(b));
  }, [siblings, selection.ways]);
  const kvsOpts = useMemo(() => {
    const set = new Set<string>();
    for (const row of siblings) {
      if (selection.ways && row.ways !== selection.ways) continue;
      if (selection.dn && row.dn !== selection.dn) continue;
      if (row.kvs) set.add(row.kvs);
    }
    return [...set];
  }, [siblings, selection.ways, selection.dn]);
  const bodyOpts = useMemo(() => {
    const set = new Set<string>();
    for (const row of siblings) {
      if (selection.ways && row.ways !== selection.ways) continue;
      if (selection.dn && row.dn !== selection.dn) continue;
      if (selection.kvs && row.kvs !== selection.kvs) continue;
      if (row.body) set.add(row.body);
    }
    return [...set];
  }, [siblings, selection.ways, selection.dn, selection.kvs]);
  const voltageOpts = useMemo(() => {
    const set = new Set<string>();
    for (const row of siblings) {
      if (selection.ways && row.ways !== selection.ways) continue;
      if (selection.dn && row.dn !== selection.dn) continue;
      if (selection.kvs && row.kvs !== selection.kvs) continue;
      if (selection.body && row.body !== selection.body) continue;
      if (row.voltage) set.add(row.voltage);
    }
    return [...set];
  }, [siblings, selection]);
  const controlOpts = useMemo(() => {
    const set = new Set<string>();
    for (const row of siblings) {
      if (selection.ways && row.ways !== selection.ways) continue;
      if (selection.dn && row.dn !== selection.dn) continue;
      if (selection.kvs && row.kvs !== selection.kvs) continue;
      if (selection.body && row.body !== selection.body) continue;
      if (selection.voltage && row.voltage !== selection.voltage) continue;
      if (row.control) set.add(row.control);
    }
    const order = ["A", "AS", "D", "DS", "DST", "M"];
    return [...set].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  }, [siblings, selection]);

  function patch(partial: Partial<VariantSelection>) {
    const match = applyVariantPatch(siblings, selection, partial);
    if (!match) return;
    setSelection(selectionFromSibling(match));
    if (match.slug !== currentSlug) {
      onEditionChange?.(match.slug);
      navigate(catalogSkuPath(categorySlug, match.slug), {
        replace: true,
        state: { softNav: true },
      });
    }
  }

  if (siblings.length <= 1) return null;

  return (
    <div className={styles.picker} aria-label="Варианты исполнения">
      <p className={styles.title}>Вариант исполнения</p>
      <div className={styles.axes}>
        <AxisSelect
          label="Вид"
          value={selection.ways}
          options={waysOpts}
          onChange={(ways) => patch({ ways })}
        />
        <AxisSelect
          label="DN"
          value={selection.dn}
          options={dnOpts}
          onChange={(dn) => patch({ dn })}
        />
        <AxisSelect
          label="Kvs"
          value={selection.kvs}
          options={kvsOpts}
          onChange={(kvs) => patch({ kvs })}
        />
        <AxisSelect
          label="Корпус"
          value={selection.body}
          options={bodyOpts}
          onChange={(body) => patch({ body })}
        />
        <AxisSelect
          label="Напряжение"
          value={selection.voltage}
          options={voltageOpts}
          onChange={(voltage) => patch({ voltage })}
        />
        <AxisSelect
          label="Управление"
          value={selection.control}
          options={controlOpts}
          onChange={(control) => patch({ control })}
        />
      </div>
    </div>
  );
}
