import { CSSProperties, useMemo, useState } from "react";

const NHL_ASSET_HOST = "https://assets.nhle.com";

const TEAM_ALIASES: Record<string, string> = {
  ARI: "ARI",
  UTA: "UTA",
};

const TEAM_THEMES: Record<string, { primary: string; secondary: string; text: string }> = {
  ANA: { primary: "#FC4C02", secondary: "#B9975B", text: "#FFFFFF" },
  BOS: { primary: "#FFB81C", secondary: "#111111", text: "#111111" },
  BUF: { primary: "#003087", secondary: "#FFB81C", text: "#FFFFFF" },
  CGY: { primary: "#C8102E", secondary: "#F1BE48", text: "#FFFFFF" },
  CAR: { primary: "#CC0000", secondary: "#111111", text: "#FFFFFF" },
  CHI: { primary: "#CF0A2C", secondary: "#111111", text: "#FFFFFF" },
  COL: { primary: "#6F263D", secondary: "#236192", text: "#FFFFFF" },
  CBJ: { primary: "#002654", secondary: "#CE1126", text: "#FFFFFF" },
  DAL: { primary: "#006847", secondary: "#8F8F8C", text: "#FFFFFF" },
  DET: { primary: "#CE1126", secondary: "#FFFFFF", text: "#FFFFFF" },
  EDM: { primary: "#041E42", secondary: "#FF4C00", text: "#FFFFFF" },
  FLA: { primary: "#C8102E", secondary: "#041E42", text: "#FFFFFF" },
  LAK: { primary: "#111111", secondary: "#A2AAAD", text: "#FFFFFF" },
  MIN: { primary: "#154734", secondary: "#A6192E", text: "#FFFFFF" },
  MTL: { primary: "#AF1E2D", secondary: "#192168", text: "#FFFFFF" },
  NSH: { primary: "#FFB81C", secondary: "#041E42", text: "#111111" },
  NJD: { primary: "#CE1126", secondary: "#111111", text: "#FFFFFF" },
  NYI: { primary: "#00539B", secondary: "#F47D30", text: "#FFFFFF" },
  NYR: { primary: "#0038A8", secondary: "#CE1126", text: "#FFFFFF" },
  OTT: { primary: "#C52032", secondary: "#C2912C", text: "#FFFFFF" },
  PHI: { primary: "#F74902", secondary: "#111111", text: "#FFFFFF" },
  PIT: { primary: "#FFB81C", secondary: "#111111", text: "#111111" },
  SEA: { primary: "#001628", secondary: "#99D9D9", text: "#FFFFFF" },
  SJS: { primary: "#006D75", secondary: "#111111", text: "#FFFFFF" },
  STL: { primary: "#002F87", secondary: "#FCB514", text: "#FFFFFF" },
  TBL: { primary: "#002868", secondary: "#FFFFFF", text: "#FFFFFF" },
  TOR: { primary: "#00205B", secondary: "#FFFFFF", text: "#FFFFFF" },
  UTA: { primary: "#71AFE5", secondary: "#111111", text: "#111111" },
  VAN: { primary: "#00205B", secondary: "#00843D", text: "#FFFFFF" },
  VGK: { primary: "#B4975A", secondary: "#333F42", text: "#111111" },
  WSH: { primary: "#041E42", secondary: "#C8102E", text: "#FFFFFF" },
  WPG: { primary: "#041E42", secondary: "#004C97", text: "#FFFFFF" },
};

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function normalizeTeamAbbrev(team: string): string {
  const normalized = team.trim().toUpperCase();
  if (!normalized) return normalized;
  return TEAM_ALIASES[normalized] ?? normalized;
}

export function playerHeadshotUrl(playerId: string): string {
  return `${NHL_ASSET_HOST}/mugs/nhl/latest/${playerId}.png`;
}

export function teamLogoUrl(team: string, variant: "light" | "dark" = "light"): string {
  const abbrev = normalizeTeamAbbrev(team);
  return `${NHL_ASSET_HOST}/logos/nhl/svg/${abbrev}_${variant}.svg`;
}

function isLikelyNumericId(value: string | null | undefined): boolean {
  if (!value) return false;
  return /^\d+$/.test(value.trim());
}

function unique(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    if (!value) continue;
    const normalized = value.trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    out.push(normalized);
  }
  return out;
}

function normalizeAssetUrl(value?: string | null): string | null {
  if (!value) return null;
  const normalized = value.trim();
  if (!normalized) return null;
  if (normalized.startsWith("//")) return `https:${normalized}`;
  if (normalized.startsWith("/")) return `${NHL_ASSET_HOST}${normalized}`;
  return normalized;
}

function playerHeadshotCandidates(playerId: string): string[] {
  return unique([
    playerHeadshotUrl(playerId),
    `${NHL_ASSET_HOST}/mugs/nhl/${playerId}.png`,
  ]);
}

function headshotCandidates(playerId: string, externalId?: string | null, headshotUrl?: string | null): string[] {
  const numericExternal = isLikelyNumericId(externalId) ? externalId!.trim() : null;
  const numericPlayer = isLikelyNumericId(playerId) ? playerId.trim() : null;
  return unique([
    normalizeAssetUrl(headshotUrl),
    ...(numericExternal ? playerHeadshotCandidates(numericExternal) : []),
    ...(numericPlayer ? playerHeadshotCandidates(numericPlayer) : []),
  ]);
}

export function teamTheme(team: string): { primary: string; secondary: string; text: string } {
  const normalized = normalizeTeamAbbrev(team);
  return TEAM_THEMES[normalized] ?? { primary: "#2E6AA8", secondary: "#10243F", text: "#FFFFFF" };
}

export function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace("#", "");
  if (![3, 6].includes(normalized.length)) return `rgba(46,106,168,${alpha})`;
  const expanded =
    normalized.length === 3 ? normalized.split("").map((char) => `${char}${char}`).join("") : normalized;
  const int = Number.parseInt(expanded, 16);
  const r = (int >> 16) & 255;
  const g = (int >> 8) & 255;
  const b = int & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function teamCardStyle(team: string, emphasis: "normal" | "strong" = "normal"): CSSProperties {
  const theme = teamTheme(team);
  const tintAlpha = emphasis === "strong" ? 0.14 : 0.1;
  const borderAlpha = emphasis === "strong" ? 0.6 : 0.42;
  const shadowAlpha = emphasis === "strong" ? 0.24 : 0.14;
  return {
    borderColor: hexToRgba(theme.primary, borderAlpha),
    background: `linear-gradient(180deg, ${hexToRgba(theme.primary, tintAlpha)} 0%, rgba(16, 20, 26, 0.97) 40%)`,
    boxShadow: `inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 18px ${hexToRgba(theme.primary, shadowAlpha)}`,
  };
}

type PlayerAvatarProps = {
  playerId: string;
  externalId?: string | null;
  headshotUrl?: string | null;
  name: string;
  size?: "default" | "small" | "large";
  className?: string;
};

export function PlayerAvatar({
  playerId,
  externalId,
  headshotUrl,
  name,
  size = "default",
  className = "",
}: PlayerAvatarProps) {
  const [sourceIndex, setSourceIndex] = useState(0);
  const fallback = useMemo(() => initials(name), [name]);
  const sources = useMemo(() => headshotCandidates(playerId, externalId, headshotUrl), [playerId, externalId, headshotUrl]);
  const currentSource = sources[sourceIndex];
  const imageFailed = !currentSource;
  const sizeClass = size === "small" ? "small" : size === "large" ? "large" : "";
  const classes = ["avatar", sizeClass, className].filter(Boolean).join(" ");

  return (
    <div className={classes} aria-label={`${name} avatar`}>
      {imageFailed ? (
        <span>{fallback}</span>
      ) : (
        <img
          className="avatar-img"
          src={currentSource}
          alt={`${name} headshot`}
          loading="lazy"
          decoding="async"
          onError={() => {
            setSourceIndex((index) => index + 1);
          }}
        />
      )}
    </div>
  );
}

type TeamLogoProps = {
  team: string;
  variant?: "light" | "dark";
  className?: string;
};

export function TeamLogo({ team, variant = "light", className = "" }: TeamLogoProps) {
  const [imageFailed, setImageFailed] = useState(false);
  if (imageFailed || !team) return null;

  return (
    <img
      className={["team-logo", className].filter(Boolean).join(" ")}
      src={teamLogoUrl(team, variant)}
      alt={`${team} logo`}
      loading="lazy"
      decoding="async"
      onError={() => setImageFailed(true)}
    />
  );
}
