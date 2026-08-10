export type BallValveKitOptions = {
  drive_families: string[];
  suffixes: string[];
  bracket_by_drive: Record<string, string>;
  bracket_hint: string;
};

export type BallValveKitSelection = {
  includeActuator: boolean;
  driveFamily: string;
  suffix: string;
  includeBracket: boolean;
  bracket: string;
};

export function defaultBallValveKitSelection(
  kit: BallValveKitOptions,
): BallValveKitSelection {
  const driveFamily = kit.drive_families[0] ?? "";
  return {
    includeActuator: false,
    driveFamily,
    suffix: kit.suffixes[0] ?? "-D",
    includeBracket: false,
    bracket: kit.bracket_by_drive[driveFamily] ?? "BR-M",
  };
}

export function resolveBracketForDrive(
  kit: BallValveKitOptions,
  driveFamily: string,
): string {
  return kit.bracket_by_drive[driveFamily] ?? "BR-M";
}

export function formatDriveCode(family: string, suffix: string): string {
  return `${family}${suffix}`;
}

export function appendBallValveKitToMessage(
  baseMessage: string,
  selection: BallValveKitSelection,
): string {
  if (!selection.includeActuator || !selection.driveFamily) {
    return baseMessage.trim();
  }
  const driveCode = formatDriveCode(selection.driveFamily, selection.suffix);
  const lines = ["", "Дополнительно к комплекту:", `- Электропривод: ${driveCode}`];
  if (selection.includeBracket && selection.bracket) {
    lines.push(`- Кронштейн: ${selection.bracket}`);
  }
  return `${baseMessage.trim()}${lines.join("\n")}`;
}
