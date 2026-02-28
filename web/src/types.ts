export type SetupStatus = {
  setup_required: boolean;
  user_count: number;
  app_mode: string;
  enable_registration: boolean;
  yahoo_enabled: boolean;
};

export type AuthSession = {
  accessToken: string;
  refreshToken: string;
};

export type User = {
  id: string;
  username: string;
  email: string;
  display_name: string;
  scans_created: number;
  created_at: string;
};

export type Player = {
  id: string;
  name: string;
  team: string;
  position: string;
  number?: number;
  current_streamer_score: number;
  ownership_percentage: number;
};

export type ScanRule = {
  id?: string;
  stat: string;
  comparator: string;
  value: number;
  window: string;
  compare_window?: string | null;
};

export type Scan = {
  id: string;
  name: string;
  description: string;
  is_preset: boolean;
  is_followed: boolean;
  is_hidden: boolean;
  alerts_enabled: boolean;
  match_count: number;
  rules: ScanRule[];
};

export type League = {
  id: string;
  name: string;
  league_type: string;
  scoring_weights: Record<string, number>;
  is_active: boolean;
};
