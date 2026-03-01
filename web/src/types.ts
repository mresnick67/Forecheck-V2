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
  external_id?: string | null;
  name: string;
  team: string;
  position: string;
  number?: number;
  headshot_url?: string | null;
  current_streamer_score: number;
};

export type ExplorePlayer = Player & {
  window: string;
  window_streamer_score: number;
  games_played: number;
  goalie_games_started?: number | null;
  points_per_game?: number | null;
  shots_per_game?: number | null;
  hits_per_game?: number | null;
  blocks_per_game?: number | null;
  time_on_ice_per_game?: number | null;
  save_percentage?: number | null;
  goals_against_average?: number | null;
  goalie_wins?: number | null;
  weekly_games?: number | null;
  weekly_light_games?: number | null;
  weekly_heavy_games?: number | null;
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
  user_id?: string | null;
  name: string;
  description: string;
  position_filter?: string | null;
  is_preset: boolean;
  is_followed: boolean;
  is_hidden: boolean;
  alerts_enabled: boolean;
  match_count: number;
  last_evaluated?: string | null;
  rules: ScanRule[];
};

export type League = {
  id: string;
  name: string;
  league_type: string;
  scoring_weights: Record<string, number>;
  is_active: boolean;
  updated_at?: string;
};

export type StreamerScoreComponent = {
  key: string;
  label: string;
  enabled: boolean;
  metric_value?: number | null;
  cap?: number | null;
  weight?: number | null;
  normalized_value?: number | null;
  raw_contribution: number;
  base_contribution: number;
  final_contribution: number;
  notes?: string | null;
};

export type StreamerScoreBreakdown = {
  player_id: string;
  window: string;
  position: string;
  trend_direction?: string | null;
  games_played: number;
  base_score_before_cap: number;
  base_score: number;
  base_cap_factor: number;
  score_before_sample_penalty?: number | null;
  sample_factor?: number | null;
  league_fit_score?: number | null;
  league_blend_weight: number;
  league_component_contribution: number;
  final_score: number;
  components: StreamerScoreComponent[];
};
