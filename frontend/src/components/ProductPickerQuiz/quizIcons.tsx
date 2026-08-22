import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const W = 24;
const SW = 1.85;
const SW_FINE = 1.35;

function baseProps(props: IconProps) {
  return {
    width: 24,
    height: 24,
    viewBox: `0 0 ${W} ${W}`,
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
    "aria-hidden": true,
    ...props,
  } as const;
}

function ink(width = SW) {
  return {
    stroke: "currentColor",
    strokeWidth: width,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
}

function fillInk() {
  return { fill: "currentColor", stroke: "none" as const };
}

function Svg(props: IconProps & { children: ReactNode }) {
  const { children, ...rest } = props;
  return <svg {...baseProps(rest)}>{children}</svg>;
}

/** Motor box + shaft. */
function actuatorMotor(x: number, y: number, w = 10, h = 6) {
  const cx = x + w / 2;
  return (
    <>
      <rect x={x} y={y} width={w} height={h} rx={1.25} {...ink()} />
      <path d={`M${cx} ${y + h}v2.2`} {...ink()} />
    </>
  );
}

/** Rectangular damper blade in duct. */
function rectDamper(x: number, y: number, w: number, h: number) {
  const cx = x + w / 2;
  return (
    <>
      <rect x={x} y={y} width={w} height={h} rx={1} {...ink()} />
      <path d={`M${cx} ${y + 1.2}v${h - 2.4}`} {...ink(SW_FINE)} />
    </>
  );
}

/** Horizontal pipe with ball bore. */
function ballBody(cx: number, cy: number, bodyR = 3.8, portR = 1.2) {
  return (
    <>
      <path d={`M4 ${cy}h16`} {...ink(SW)} />
      <circle cx={cx} cy={cy} r={bodyR} {...ink()} />
      <circle cx={cx} cy={cy} r={portR} {...ink(SW_FINE)} />
    </>
  );
}

/** T-handle stem on ball valve. */
function valveStem(cx: number, top = 6.5) {
  return (
    <>
      <path d={`M${cx} ${top + 2.8}V${top}`} {...ink()} />
      <path d={`M${cx - 2.2} ${top}h4.4`} {...ink()} />
    </>
  );
}

function flowRipples(cx: number, cy: number, count: number) {
  const lines = [];
  for (let i = 0; i < count; i += 1) {
    const ox = cx - (count - 1) * 1.4 + i * 2.8;
    lines.push(
      <path
        key={i}
        d={`M${ox - 1} ${cy + 1.5}q1 1.2 2 0t2 0`}
        {...ink(SW_FINE)}
      />,
    );
  }
  return <>{lines}</>;
}

function pressureGauge(level: number, extra?: ReactNode) {
  const angle = (-130 + level * 260) * (Math.PI / 180);
  const nx = 12 + Math.cos(angle) * 4.6;
  const ny = 13 + Math.sin(angle) * 4.6;
  return (
    <>
      <path d="M7 13a5 5 0 1 1 10 0" {...ink()} />
      <path d="M12 8.2v1.2" {...ink(SW_FINE)} />
      <path d={`M12 13L${nx.toFixed(2)} ${ny.toFixed(2)}`} {...ink(SW)} />
      <circle cx={12} cy={13} r={0.9} {...fillInk()} />
      {extra}
    </>
  );
}

function dnPipe(bore: number, label: string) {
  return (
    <>
      <path d="M5 10.5h14" {...ink(SW)} />
      <circle cx={12} cy={10.5} r={bore + 1.6} {...ink()} />
      <circle cx={12} cy={10.5} r={bore} {...ink(SW_FINE)} />
      <text
        x={12}
        y={19.5}
        textAnchor="middle"
        fontSize="5.5"
        fontWeight="700"
        fill="currentColor"
        stroke="none"
      >
        {label}
      </text>
    </>
  );
}

function areaFrame(w: number, h: number) {
  const x = (W - w) / 2;
  const y = (W - h) / 2;
  const cx = x + w / 2;
  return (
    <>
      <rect x={x} y={y} width={w} height={h} rx={1} {...ink()} />
      <path d={`M${cx} ${y + 1}v${h - 2}`} {...ink(SW_FINE)} />
    </>
  );
}

export function IconActuator(props: IconProps) {
  return (
    <Svg {...props}>
      {actuatorMotor(7, 4)}
      {rectDamper(5, 13, 14, 7)}
      <circle cx={12} cy={16.5} r={0.85} {...fillInk()} />
    </Svg>
  );
}

export function IconBallValve(props: IconProps) {
  return (
    <Svg {...props}>
      {ballBody(12, 12.5, 3.6, 1.1)}
      {valveStem(12, 5.5)}
    </Svg>
  );
}

export function IconKit(props: IconProps) {
  return (
    <Svg {...props}>
      {actuatorMotor(12.5, 4, 8, 5.5)}
      {ballBody(8.5, 15.5, 3.2, 1)}
      {valveStem(8.5, 9.5)}
      <path d="M12.5 11.5h2.8l1.2 2.2" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconAdapter(props: IconProps) {
  return (
    <Svg {...props}>
      {actuatorMotor(8, 4, 8, 5.5)}
      {ballBody(12, 16, 2.8, 0.9)}
      <path d="M10 11.5h4" {...ink(SW_FINE)} />
    </Svg>
  );
}

/** BR-M — привод MU/MQU без пружины. */
export function IconAdapterBrM(props: IconProps) {
  return (
    <Svg {...props}>
      {actuatorMotor(7.5, 3.5, 9, 5.5)}
      {ballBody(12, 15.5, 2.6, 0.75)}
      <text
        x={12}
        y={21.5}
        textAnchor="middle"
        fontSize="4.5"
        fontWeight="700"
        fill="currentColor"
        stroke="none"
      >
        M
      </text>
    </Svg>
  );
}

/** BR-ML — привод FU с пружиной. */
export function IconAdapterBrMl(props: IconProps) {
  return (
    <Svg {...props}>
      {actuatorMotor(7.5, 3.5, 9, 5.5)}
      <path
        d="M9 10c1-1 2-1 3 0s2 1 3 0"
        {...ink(SW_FINE)}
      />
      {ballBody(12, 15.5, 2.6, 0.75)}
      <text
        x={12}
        y={21.5}
        textAnchor="middle"
        fontSize="3.8"
        fontWeight="700"
        fill="currentColor"
        stroke="none"
      >
        ML
      </text>
    </Svg>
  );
}

export function IconVentGeneral(props: IconProps) {
  return (
    <Svg {...props}>
      {rectDamper(4, 8.5, 16, 8)}
      <path d="M6 12.5h2.5M6 12l1.2 1.2M6 13l1.2-1.2" {...ink(SW_FINE)} />
      <path d="M18 12.5h-2.5M18 12l-1.2 1.2M18 13l-1.2-1.2" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconFireDamper(props: IconProps) {
  return (
    <Svg {...props}>
      {rectDamper(4, 12, 16, 7)}
      <path
        d="M12 5.5c-1.2 1.5-1.8 2.6-1.8 3.8a1.8 1.8 0 0 0 3.6 0c0-1.2-.6-2.3-1.8-3.8Z"
        {...ink()}
      />
    </Svg>
  );
}

export function IconSmokeExtract(props: IconProps) {
  return (
    <Svg {...props}>
      {rectDamper(4, 13, 16, 6.5)}
      <path
        d="M8.5 6.5c.4.8.4 1.5 0 2.1M12 5.5c.5 1 .5 1.8 0 2.6M15.5 6.5c.4.8.4 1.5 0 2.1"
        {...ink(SW_FINE)}
      />
    </Svg>
  );
}

export function IconFailsafe(props: IconProps) {
  return (
    <Svg {...props}>
      {actuatorMotor(6.5, 3.5, 11, 6)}
      {rectDamper(5, 11.5, 14, 5.5)}
      <path
        d="M8.5 19c1-1.2 2-1.2 3 0s2 1.2 3 0 2-1.2 3 0"
        {...ink(SW_FINE)}
      />
    </Svg>
  );
}

export function IconFastDamper(props: IconProps) {
  return (
    <Svg {...props}>
      {rectDamper(3.5, 9, 12, 7.5)}
      <path d="M17.5 10.5l2.2 1.8-2.2 1.8M17.5 14.5l2.2 1.8-2.2 1.8" {...ink()} />
    </Svg>
  );
}

export function IconSpringReturn(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M7 8.5c1.2-1.5 2.4-1.5 3.6 0s2.4 1.5 3.6 0 2.4-1.5 3.6 0"
        {...ink(SW_FINE)}
      />
      <path
        d="M7 13c1.2-1.5 2.4-1.5 3.6 0s2.4 1.5 3.6 0 2.4-1.5 3.6 0"
        {...ink(SW_FINE)}
      />
      <path d="M12 16.5V19M9.5 19h5" {...ink()} />
    </Svg>
  );
}

export function IconElectronicFailsafe(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x={5.5} y={6} width={13} height={9} rx={1.25} {...ink()} />
      <path d="M8.5 9h7M8.5 12h4.5" {...ink(SW_FINE)} />
      <path d="M16.5 16.5a3.2 3.2 0 1 0-1.2-5.2" {...ink(SW_FINE)} />
      <path d="M15.5 12.5l1.4-1.4v2.6" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconVoltage24(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x={5} y={6.5} width={14} height={11} rx={1.5} {...ink()} />
      <path d="M8 10.5h8" {...ink(SW)} />
      <path d="M8 14h8" strokeDasharray="2.2 1.8" {...ink(SW_FINE)} />
      <text
        x={12}
        y={19.8}
        textAnchor="middle"
        fontSize="4.5"
        fontWeight="700"
        fill="currentColor"
        stroke="none"
      >
        DC
      </text>
    </Svg>
  );
}

export function IconVoltage230(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 7.5c0-.8.7-1.5 1.5-1.5h2c.8 0 1.5.7 1.5 1.5V11" {...ink()} />
      <path d="M12 11v4.5" {...ink()} />
      <path d="M9.5 15.5h5" {...ink()} />
      <path d="M10.5 7.5h3" {...ink(SW_FINE)} />
      <path d="M7 19.5h10" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconControlOnOff(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x={5} y={9} width={14} height={7} rx={3.5} {...ink()} />
      <circle cx={9} cy={12.5} r={2.3} {...fillInk()} />
    </Svg>
  );
}

export function IconControlModulating(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 9.5c2-2.2 3.2-3 5-3s3 0.8 5 3" {...ink(SW_FINE)} />
      <path d="M4 17h16" {...ink(SW_FINE)} />
      <circle cx={15.5} cy={17} r={2} {...ink()} />
      <path d="M15.5 15v-1.5" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconAreaUpTo03(props: IconProps) {
  return <Svg {...props}>{areaFrame(8, 6)}</Svg>;
}

export function IconArea03To06(props: IconProps) {
  return <Svg {...props}>{areaFrame(10, 7)}</Svg>;
}

export function IconArea06To10(props: IconProps) {
  return <Svg {...props}>{areaFrame(12, 8)}</Svg>;
}

export function IconArea10To16(props: IconProps) {
  return <Svg {...props}>{areaFrame(14, 9)}</Svg>;
}

export function IconArea16To25(props: IconProps) {
  return <Svg {...props}>{areaFrame(16, 10)}</Svg>;
}

export function IconArea25To40(props: IconProps) {
  return <Svg {...props}>{areaFrame(18, 11)}</Svg>;
}

export function IconAreaOver4(props: IconProps) {
  return (
    <Svg {...props}>
      {areaFrame(19, 12)}
      <path d="M19.5 6v12M21 7.5h-3M21 16.5h-3" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconDamperRound(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x={4} y={8} width={16} height={9} rx={1} {...ink()} />
      <circle cx={12} cy={12.5} r={3.2} {...ink()} />
      <path d="M12 9.3v6.4" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconDamperRect(props: IconProps) {
  return <Svg {...props}>{rectDamper(4, 8, 16, 9)}</Svg>;
}

export function IconDamperGate(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x={4} y={8} width={16} height={9} rx={1} {...ink()} />
      <path d="M6.5 12.5h11" {...ink(SW)} />
      <path d="M12 5.5v2.2M10.5 5.5h3" {...ink()} />
    </Svg>
  );
}

export function IconPressureLow(props: IconProps) {
  return <Svg {...props}>{pressureGauge(0.1)}</Svg>;
}

export function IconPressureMedium(props: IconProps) {
  return <Svg {...props}>{pressureGauge(0.42)}</Svg>;
}

export function IconPressureHigh(props: IconProps) {
  return <Svg {...props}>{pressureGauge(0.68)}</Svg>;
}

export function IconPressureVeryHigh(props: IconProps) {
  return (
    <Svg {...props}>
      {pressureGauge(
        0.9,
        <path d="M8.5 9.5l1 1M15.5 9.5l-1 1" {...ink(SW_FINE)} />,
      )}
    </Svg>
  );
}

export function IconDn15(props: IconProps) {
  return <Svg {...props}>{dnPipe(1.4, "15")}</Svg>;
}

export function IconDn20(props: IconProps) {
  return <Svg {...props}>{dnPipe(1.7, "20")}</Svg>;
}

export function IconDn25(props: IconProps) {
  return <Svg {...props}>{dnPipe(2, "25")}</Svg>;
}

export function IconDn32(props: IconProps) {
  return <Svg {...props}>{dnPipe(2.3, "32")}</Svg>;
}

export function IconDn40(props: IconProps) {
  return <Svg {...props}>{dnPipe(2.6, "40")}</Svg>;
}

export function IconDn50(props: IconProps) {
  return <Svg {...props}>{dnPipe(2.9, "50")}</Svg>;
}

export function IconKvsUpTo25(props: IconProps) {
  return (
    <Svg {...props}>
      {ballBody(12, 10, 3.2, 0.75)}
      {valveStem(12, 3.5)}
      {flowRipples(12, 15.5, 1)}
    </Svg>
  );
}

export function IconKvs25To6(props: IconProps) {
  return (
    <Svg {...props}>
      {ballBody(12, 10, 3.2, 1.1)}
      {valveStem(12, 3.5)}
      {flowRipples(12, 15.5, 2)}
    </Svg>
  );
}

export function IconKvs6To16(props: IconProps) {
  return (
    <Svg {...props}>
      {ballBody(12, 10, 3.2, 1.45)}
      {valveStem(12, 3.5)}
      {flowRipples(12, 15.5, 3)}
    </Svg>
  );
}

export function IconKvs16To40(props: IconProps) {
  return (
    <Svg {...props}>
      {ballBody(12, 10, 3.2, 1.75)}
      {valveStem(12, 3.5)}
      {flowRipples(12, 15.5, 4)}
    </Svg>
  );
}

export function IconKvsOver40(props: IconProps) {
  return (
    <Svg {...props}>
      {ballBody(12, 10, 3.2, 2.05)}
      {valveStem(12, 3.5)}
      {flowRipples(12, 15.5, 5)}
    </Svg>
  );
}

export function IconValve2Way(props: IconProps) {
  return (
    <Svg {...props}>
      {ballBody(12, 12.5, 3.5, 1.2)}
      <path d="M12 9v7" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconValve3Way(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 6.5v11.5M6 12.5h12" {...ink(SW)} />
      <circle cx={12} cy={12.5} r={2.8} {...ink()} />
      <path d="M12 9.7v5.6" {...ink(SW_FINE)} />
    </Svg>
  );
}

export function IconSkipUnknown(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx={12} cy={12} r={7} {...ink()} />
      <path
        d="M9.8 9.5a2.4 2.4 0 0 1 3.9 1.9c0 1.4-1.6 1.8-1.6 3.1"
        {...ink(SW_FINE)}
      />
      <circle cx={12} cy={17.2} r={0.75} {...fillInk()} />
    </Svg>
  );
}
