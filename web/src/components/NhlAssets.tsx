import { useMemo, useState } from "react";

const NHL_ASSET_HOST = "https://assets.nhle.com";

const TEAM_ALIASES: Record<string, string> = {
  ARI: "ARI",
  UTA: "UTA",
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

type PlayerAvatarProps = {
  playerId: string;
  name: string;
  size?: "default" | "small" | "large";
  className?: string;
};

export function PlayerAvatar({ playerId, name, size = "default", className = "" }: PlayerAvatarProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const fallback = useMemo(() => initials(name), [name]);
  const sizeClass = size === "small" ? "small" : size === "large" ? "large" : "";
  const classes = ["avatar", sizeClass, className].filter(Boolean).join(" ");

  return (
    <div className={classes} aria-label={`${name} avatar`}>
      {imageFailed ? (
        <span>{fallback}</span>
      ) : (
        <img
          className="avatar-img"
          src={playerHeadshotUrl(playerId)}
          alt={`${name} headshot`}
          loading="lazy"
          decoding="async"
          onError={() => setImageFailed(true)}
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
