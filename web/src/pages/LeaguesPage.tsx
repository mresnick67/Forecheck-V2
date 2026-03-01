import { FormEvent, useEffect, useMemo, useState } from "react";

import { authRequest } from "../api";
import type { AuthSession, League } from "../types";

type LeaguesPageProps = {
  session: AuthSession;
  onSession: (session: AuthSession | null) => void;
};

type LeagueDraft = {
  name: string;
  league_type: string;
  scoring_weights: Record<string, number>;
};

const CATEGORIES_DEFAULT_WEIGHTS: Record<string, number> = {
  goals: 1,
  assists: 1,
  points: 1,
  plus_minus: 1,
  pim: 1,
  power_play_points: 1,
  shots: 1,
  hits: 1,
  blocks: 1,
  wins: 1,
  save_percentage: 1,
  goals_against_average: 1,
  saves: 1,
  shutouts: 1,
};

const POINTS_DEFAULT_WEIGHTS: Record<string, number> = {
  goals: 3,
  assists: 2,
  plus_minus: 0.5,
  pim: 0,
  power_play_points: 1,
  shorthanded_points: 2,
  shots: 0.4,
  hits: 0.2,
  blocks: 0.2,
  wins: 3,
  saves: 0.2,
  goals_against: -1,
  shutouts: 5,
};

function defaultWeights(leagueType: string): Record<string, number> {
  return {
    ...(leagueType === "categories" ? CATEGORIES_DEFAULT_WEIGHTS : POINTS_DEFAULT_WEIGHTS),
  };
}

function formatWeightName(stat: string): string {
  return stat
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function sortedWeights(weights: Record<string, number>): Array<[string, number]> {
  return Object.entries(weights).sort(([a], [b]) => a.localeCompare(b));
}

export default function LeaguesPage({ session, onSession }: LeaguesPageProps) {
  const [leagues, setLeagues] = useState<League[]>([]);
  const [draftById, setDraftById] = useState<Record<string, LeagueDraft>>({});

  const [name, setName] = useState("");
  const [leagueType, setLeagueType] = useState("categories");
  const [newWeights, setNewWeights] = useState<Record<string, number>>(defaultWeights("categories"));
  const [newCustomStat, setNewCustomStat] = useState("");
  const [newCustomWeight, setNewCustomWeight] = useState("1");

  const [savingLeagueId, setSavingLeagueId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sortedLeagues = useMemo(
    () =>
      [...leagues].sort((a, b) => {
        if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
        return a.name.localeCompare(b.name);
      }),
    [leagues],
  );

  function normalizeStatKey(value: string): string {
    return value.trim().toLowerCase().replace(/\s+/g, "_");
  }

  async function loadLeagues() {
    setLoading(true);
    try {
      const response = await authRequest<League[]>("/leagues", session, onSession);
      setLeagues(response);
      setDraftById((prev) => {
        const next = { ...prev };
        for (const league of response) {
          next[league.id] = {
            name: league.name,
            league_type: league.league_type,
            scoring_weights: { ...(league.scoring_weights ?? {}) },
          };
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load leagues");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadLeagues();
  }, []);

  useEffect(() => {
    setNewWeights(defaultWeights(leagueType));
  }, [leagueType]);

  function updateNewWeight(stat: string, value: number) {
    setNewWeights((prev) => ({ ...prev, [stat]: value }));
  }

  function addNewCustomStat() {
    const key = normalizeStatKey(newCustomStat);
    if (!key) return;
    const value = Number(newCustomWeight);
    setNewWeights((prev) => ({ ...prev, [key]: Number.isFinite(value) ? value : 0 }));
    setNewCustomStat("");
    setNewCustomWeight("1");
  }

  function updateLeagueDraft(leagueId: string, patch: Partial<LeagueDraft>) {
    setDraftById((prev) => ({
      ...prev,
      [leagueId]: {
        ...(prev[leagueId] ?? { name: "", league_type: "categories", scoring_weights: {} }),
        ...patch,
      },
    }));
  }

  function updateLeagueWeight(leagueId: string, stat: string, value: number) {
    setDraftById((prev) => {
      const draft = prev[leagueId];
      if (!draft) return prev;
      return {
        ...prev,
        [leagueId]: {
          ...draft,
          scoring_weights: {
            ...draft.scoring_weights,
            [stat]: value,
          },
        },
      };
    });
  }

  async function createLeague(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setSavingLeagueId("create");
    try {
      await authRequest("/leagues", session, onSession, {
        method: "POST",
        json: {
          name,
          league_type: leagueType,
          scoring_weights: newWeights,
          is_active: leagues.length === 0,
        },
      });
      setName("");
      setLeagueType("categories");
      setNewWeights(defaultWeights("categories"));
      setStatus("League profile created.");
      await loadLeagues();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create league");
    } finally {
      setSavingLeagueId(null);
    }
  }

  async function saveLeague(league: League) {
    const draft = draftById[league.id];
    if (!draft) return;
    setError(null);
    setStatus(null);
    setSavingLeagueId(league.id);
    try {
      await authRequest(`/leagues/${league.id}`, session, onSession, {
        method: "PUT",
        json: {
          name: draft.name,
          league_type: draft.league_type,
          scoring_weights: draft.scoring_weights,
        },
      });
      setStatus(`Saved ${draft.name}.`);
      await loadLeagues();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save league profile");
    } finally {
      setSavingLeagueId(null);
    }
  }

  async function setActiveLeague(leagueId: string) {
    setError(null);
    setStatus(null);
    setSavingLeagueId(leagueId);
    try {
      await authRequest(`/leagues/${leagueId}`, session, onSession, {
        method: "PUT",
        json: { is_active: true },
      });
      setStatus("Active league updated.");
      await loadLeagues();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set active league");
    } finally {
      setSavingLeagueId(null);
    }
  }

  function resetLeagueDefaults(leagueId: string) {
    const draft = draftById[leagueId];
    if (!draft) return;
    updateLeagueDraft(leagueId, { scoring_weights: defaultWeights(draft.league_type) });
  }

  async function deleteLeague(leagueId: string) {
    setError(null);
    setStatus(null);
    setSavingLeagueId(leagueId);
    try {
      await authRequest(`/leagues/${leagueId}`, session, onSession, { method: "DELETE" });
      setStatus("League profile deleted.");
      await loadLeagues();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete league");
    } finally {
      setSavingLeagueId(null);
    }
  }

  return (
    <div className="page-stack leagues-stack">
      <section className="card ios-card">
        <div className="list-head">
          <h2>League Profiles</h2>
          <small className="muted">{leagues.length} saved</small>
        </div>
        <p className="muted">
          Save Yahoo-style league scoring profiles and mark one active profile. Streamer score blending uses the active
          league when enabled in Settings.
        </p>
      </section>

      <section className="card ios-card">
        <h3>Create League Profile</h3>
        <form className="scan-builder" onSubmit={createLeague}>
          <label>
            League name
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>

          <label>
            Scoring mode
            <select value={leagueType} onChange={(event) => setLeagueType(event.target.value)}>
              <option value="categories">Categories</option>
              <option value="points">Points</option>
            </select>
          </label>

          <div className="league-weight-editor">
            {sortedWeights(newWeights).map(([stat, value]) => (
              <label key={`new-${stat}`} className="league-weight-row">
                <span>{formatWeightName(stat)}</span>
                <input
                  type="number"
                  step="0.1"
                  value={value}
                  onChange={(event) => updateNewWeight(stat, Number(event.target.value) || 0)}
                />
              </label>
            ))}
          </div>

          <div className="league-custom-row">
            <input
              placeholder="custom_stat_key"
              value={newCustomStat}
              onChange={(event) => setNewCustomStat(event.target.value)}
            />
            <input
              type="number"
              step="0.1"
              value={newCustomWeight}
              onChange={(event) => setNewCustomWeight(event.target.value)}
            />
            <button type="button" onClick={addNewCustomStat}>
              Add Stat
            </button>
          </div>

          <div className="button-row">
            <button className="primary" type="submit" disabled={savingLeagueId === "create"}>
              {savingLeagueId === "create" ? "Saving..." : "Save League"}
            </button>
          </div>
        </form>
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h3>Saved Leagues</h3>
          <small className="muted">{loading ? "Loading..." : `${sortedLeagues.length} profiles`}</small>
        </div>

        {sortedLeagues.length === 0 && !loading ? (
          <p className="muted">No leagues yet. Create your first profile above.</p>
        ) : null}

        <div className="scan-list">
          {sortedLeagues.map((league) => {
            const draft = draftById[league.id];
            if (!draft) return null;
            return (
              <article key={league.id} className="scan-card league-card">
                <div className="list-head">
                  <input
                    value={draft.name}
                    onChange={(event) => updateLeagueDraft(league.id, { name: event.target.value })}
                  />
                  <span className="badge">{league.is_active ? "Active" : "Inactive"}</span>
                </div>

                <div className="button-row">
                  <select
                    value={draft.league_type}
                    onChange={(event) =>
                      updateLeagueDraft(league.id, {
                        league_type: event.target.value,
                        scoring_weights: defaultWeights(event.target.value),
                      })
                    }
                  >
                    <option value="categories">Categories</option>
                    <option value="points">Points</option>
                  </select>

                  <button
                    type="button"
                    onClick={() => void setActiveLeague(league.id)}
                    disabled={league.is_active || savingLeagueId === league.id}
                  >
                    Set Active
                  </button>
                  <button type="button" onClick={() => void resetLeagueDefaults(league.id)}>
                    Reset Defaults
                  </button>
                </div>

                <div className="league-weight-editor">
                  {sortedWeights(draft.scoring_weights).map(([stat, value]) => (
                    <label key={`${league.id}-${stat}`} className="league-weight-row">
                      <span>{formatWeightName(stat)}</span>
                      <input
                        type="number"
                        step="0.1"
                        value={value}
                        onChange={(event) =>
                          updateLeagueWeight(league.id, stat, Number(event.target.value) || 0)
                        }
                      />
                    </label>
                  ))}
                </div>

                <div className="button-row">
                  <button
                    className="primary"
                    onClick={() => void saveLeague(league)}
                    disabled={savingLeagueId === league.id}
                  >
                    {savingLeagueId === league.id ? "Saving..." : "Save Changes"}
                  </button>
                  <button className="danger" onClick={() => void deleteLeague(league.id)} disabled={savingLeagueId === league.id}>
                    Delete
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {status ? <p className="success">{status}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
