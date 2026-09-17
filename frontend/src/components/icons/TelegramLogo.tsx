type TelegramLogoProps = {
  className?: string;
  /** Accessible label; set empty to hide from screen readers when text is visible nearby. */
  title?: string;
  /** Include Telegram wordmark next to the plane mark (footer / wide buttons). */
  withWordmark?: boolean;
};

/** Shared horizontal logo canvas — aligned with MaxLogo (131×42). */
const HORIZONTAL_VIEWBOX = "0 0 131 42";

/** Icon slot width on the horizontal canvas (matches MAX bubble). */
const ICON_SLOT = 42;

/**
 * Monochrome Telegram plane mark (`currentColor`).
 * Circle + plane cutout via evenodd; path from telegram.org `t_logo.svg`.
 */
const PLANE_PATH =
  "M28.9700376,63.3244248 C47.6273373,55.1957357 60.0684594,49.8368063 66.2934036,47.2476366 " +
  "C84.0668845,39.855031 87.7600616,38.5708563 90.1672227,38.528 C90.6966555,38.5191258 " +
  "91.8804274,38.6503351 92.6472251,39.2725385 C93.294694,39.7979149 93.4728387,40.5076237 " +
  "93.5580865,41.0057381 C93.6433345,41.5038525 93.7494885,42.63857 93.6651041,43.5252052 " +
  "C92.7019529,53.6451182 88.5344133,78.2034783 86.4142057,89.5379542 C85.5170662,94.3339958 " +
  "83.750571,95.9420841 82.0403991,96.0994568 C78.3237996,96.4414641 75.5015827,93.6432685 " +
  "71.9018743,91.2836143 C66.2690414,87.5912212 63.0868492,85.2926952 57.6192095,81.6896017 " +
  "C51.3004058,77.5256038 55.3966232,75.2369981 58.9976911,71.4967761 C59.9401076,70.5179421 " +
  "76.3155302,55.6232293 76.6324771,54.2720454 C76.6721165,54.1030573 76.7089039,53.4731496 " +
  "76.3346867,53.1405352 C75.9604695,52.8079208 75.4081573,52.921662 75.0095933,53.0121213 " +
  "C74.444641,53.1403447 65.4461175,59.0880351 48.0140228,70.8551922 C45.4598218,72.6091037 " +
  "43.1463059,73.4636682 41.0734751,73.4188859 C38.7883453,73.3695169 34.3926725,72.1268388 " +
  "31.1249416,71.0646282 C27.1169366,69.7617838 23.931454,69.0729605 24.208838,66.8603276 " +
  "C24.3533167,65.7078514 25.9403832,64.5292172 28.9700376,63.3244248 Z";

const ICON_EVENODD_PATH =
  "M64 0a64 64 0 1 1 0 128 64 64 0 0 1 0-128z" + PLANE_PATH;

/** Official Telegram wordmark (horizontal logo typeface). */
const WORDMARK_PATH =
  "M44.646 34.637v-10.2H40.4v-1.623h10.945v1.623h-4.237v10.2zm15.502-.297q-1.687.496-3.198.496-2.2 " +
  "0-3.47-1.247-1.27-1.247-1.27-3.406 0-2.04 1.16-3.278 1.167-1.247 3.078-1.247 1.927 0 2.814 " +
  "1.215.887 1.215.887 3.846h-5.445q.24 2.5 2.758 2.5 1.2 0 2.686-.552zm-5.477-4.957h3.15q0-2.247-1.447" +
  "-2.247-1.47 0-1.703 2.247zm7.924 5.254V22.013h2.367v12.624zm12.488-.297q-1.687.496-3.198.496-2.2 0-3.47" +
  "-1.247-1.27-1.247-1.27-3.406 0-2.04 1.16-3.278 1.167-1.247 3.078-1.247 1.927 0 2.814 1.215.887 1.215.887 " +
  "3.846H69.64q.24 2.5 2.758 2.5 1.2 0 2.686-.552zm-5.477-4.957h3.15q0-2.247-1.447-2.247-1.47 0-1.703 2.247zm7.988 " +
  "7.98l.192-1.72q1.463.672 2.8.672 1.3 0 1.895-.56.584-.56.584-1.815v-1.2q-.863 1.895-2.854 1.895-1.567 0-2.486" +
  "-1.167-.92-1.175-.92-3.174 0-2.103 1.03-3.366 1.03-1.27 2.742-1.27 1.343 0 2.486 1.087l.248-.887h2.127v6.7q0 2.007" +
  "-.248 2.894-.24.887-.943 1.5-1.183 1.023-3.334 1.023-1.527 0-3.3-.624zm5.46-5.996V28.13q-.855-.967-1.8-.967-.895 0" +
  "-1.423.816-.528.816-.528 2.2 0 2.574 1.655 2.574 1.143 0 2.087-1.375zm5.286 3.27v-8.78h2.367v1.655q.92-1.855 2.798" +
  "-1.855.224 0 .44.048v2.1q-.504-.184-.935-.184-1.415 0-2.303 1.43v5.573zm11.752-.944q-1.183 1.143-2.534 1.143-1.15 0" +
  "-1.87-.704-.72-.704-.72-1.823 0-1.455 1.16-2.24 1.167-.792 3.334-.792h.632v-.8q0-1.367-1.56-1.367-1.383 0-2.798.784v" +
  "-1.63q1.607-.608 3.182-.608 3.446 0 3.446 2.742v3.886q0 1.03.632 1.03.144 0 .4-.088V34.6q-.752.224-1.327.224-1.455 0" +
  "-1.87-1.143zm0-1.27V30.64h-.56q-1.07 0-1.687.384-.608.384-.608 1.055 0 .488.328.823.336.328.823.328.83 0 1.703-.808zm5.325 " +
  "2.213v-8.78h2.27v1.655q1.04-1.855 2.958-1.855 1 0 1.63.488.64.488.784 1.367 1.23-1.855 2.974-1.855 2.407 0 2.407 2.654v6.324" +
  "h-2.27v-5.55q0-1.56-1.04-1.56-1.063 0-2.07 1.535v5.573h-2.27v-5.55q0-1.567-1.047-1.567-1.047 0-2.055 1.543v5.573z";

/** Scale official 128×128 mark into the left icon slot. */
const ICON_SCALE = ICON_SLOT / 128;

/** Wordmark path bbox in the ar21 horizontal layout (icon excluded). */
const WORDMARK_BBOX = {
  minX: 40.4,
  maxX: 120,
  minY: 22,
  maxY: 36,
} as const;

/** Wordmark box inside `131×42` — gap after icon; cap height aligned with MaxLogo. */
const WORDMARK_BOX = {
  x0: 46,
  x1: 130,
  y0: 11,
  y1: 32,
} as const;

const WORDMARK_SCALE_X =
  (WORDMARK_BOX.x1 - WORDMARK_BOX.x0) / (WORDMARK_BBOX.maxX - WORDMARK_BBOX.minX);

const WORDMARK_SCALE_Y =
  (WORDMARK_BOX.y1 - WORDMARK_BOX.y0) / (WORDMARK_BBOX.maxY - WORDMARK_BBOX.minY);

const WORDMARK_TRANSFORM =
  `translate(${WORDMARK_BOX.x0 - WORDMARK_BBOX.minX * WORDMARK_SCALE_X} ` +
  `${WORDMARK_BOX.y0 - WORDMARK_BBOX.minY * WORDMARK_SCALE_Y}) ` +
  `scale(${WORDMARK_SCALE_X} ${WORDMARK_SCALE_Y})`;

function TelegramIconMark({ iconOnly = false }: { iconOnly?: boolean }) {
  const scale = iconOnly ? 1 : ICON_SCALE;

  return (
    <path
      fill="currentColor"
      fillRule="evenodd"
      clipRule="evenodd"
      transform={iconOnly ? undefined : `scale(${scale})`}
      d={ICON_EVENODD_PATH}
    />
  );
}

export function TelegramLogo({
  className,
  title = "Telegram",
  withWordmark = false,
}: TelegramLogoProps) {
  const hidden = title === "";
  const a11y = hidden
    ? { "aria-hidden": true as const }
    : { role: "img" as const, "aria-label": title };

  if (withWordmark) {
    return (
      <svg
        className={className}
        viewBox={HORIZONTAL_VIEWBOX}
        {...a11y}
        xmlns="http://www.w3.org/2000/svg"
      >
        <TelegramIconMark />
        <g transform={WORDMARK_TRANSFORM}>
          <path fill="currentColor" d={WORDMARK_PATH} />
        </g>
      </svg>
    );
  }

  return (
    <svg
      className={className}
      viewBox="0 0 128 128"
      {...a11y}
      xmlns="http://www.w3.org/2000/svg"
    >
      <TelegramIconMark iconOnly />
    </svg>
  );
}
