import { CSSProperties, FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { authRequest, publicRequest } from "../api";
import type { AuthSession, Player, Scan, ScanRule } from "../types";

type ScansPageProps = {
  session: AuthSession;
  onSession: (session: AuthSession | null) => void;
};

type RuleOption = {
  value: string;
  label: string;
};

const STAT_OPTIONS: RuleOption[] = [
  { value: "points", label: "Points / GP" },
  { value: "shots", label: "Shots / GP" },
  { value: "hits", label: "Hits / GP" },
  { value: "blocks", label: "Blocks / GP" },
  { value: "power_play_points", label: "Power Play Points / GP" },
  { value: "shooting_percentage", label: "Shooting %" },
  { value: "time_on_ice_delta", label: "TOI Delta (vs compare window)" },
  { value: "goalie_starts", label: "Goalie Starts" },
  { value: "save_percentage", label: "Save %" },
  { value: "saves_per_game", label: "Saves / Game" },
  { value: "goals_against_average", label: "Goals Against Average" },
  { value: "b2b_start_opportunity", label: "B2B Spot Start Signal" },
  { value: "ownership_percentage", label: "Ownership %" },
  { value: "streamer_score", label: "Streamer Score" },
];

const COMPARATOR_OPTIONS: RuleOption[] = [
  { value: ">=", label: ">=" },
  { value: ">", label: ">" },
  { value: "<=", label: "<=" },
  { value: "<", label: "<" },
  { value: "=", label: "=" },
];

const WINDOW_OPTIONS: RuleOption[] = [
  { value: "L5", label: "L5" },
  { value: "L10", label: "L10" },
  { value: "L20", label: "L20" },
  { value: "Season", label: "Season" },
];

function scoreColor(score: number): string {
  if (score >= 75) return "#2be37d";
  if (score >= 60) return "#2bb8f1";
  if (score >= 45) return "#f6c344";
  return "#ff6f86";
}

function formatRule(rule: ScanRule): string {
  const compare = rule.compare_window ? ` vs ${rule.compare_window}` : "";
  return `${rule.stat} ${rule.comparator} ${rule.value} (${rule.window}${compare})`;
}

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function emptyRule(): ScanRule {
  return {
    stat: "points",
    comparator: ">=",
    value: 1,
    window: "L5",
    compare_window: null,
  };
}

export default function ScansPage({ session, onSession }: ScansPageProps) {
  const [scans, setScans] = useState<Scan[]>([]);
  const [selectedScanId, setSelectedScanId] = useState<string>("");
  const [evaluatedByScan, setEvaluatedByScan] = useState<Record<string, Player[]>>({});
  const [previewResults, setPreviewResults] = useState<Player[]>([]);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [positionFilter, setPositionFilter] = useState<string>("");
  const [rules, setRules] = useState<ScanRule[]>([emptyRule()]);

  const [loadingScans, setLoadingScans] = useState(false);
  const [refreshingCounts, setRefreshingCounts] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedScan = useMemo(
    () => scans.find((scan) => scan.id === selectedScanId) ?? null,
    [scans, selectedScanId],
  );
  const selectedResults = selectedScanId ? evaluatedByScan[selectedScanId] ?? [] : [];

  async function loadScans(refreshCounts: boolean, force = false): Promise<boolean> {
    setLoadingScans(true);
    setError(null);
    try {
      let response: Scan[];
      if (refreshCounts) {
        setRefreshingCounts(true);
        response = await authRequest<Scan[]>(
          `/scans/refresh-counts?include_hidden=true&stale_minutes=30&force=${force ? "true" : "false"}`,
          session,
          onSession,
          { method: "POST" },
        );
      } else {
        response = await authRequest<Scan[]>("/scans?include_hidden=true", session, onSession);
      }

      setScans(response);
      if (!selectedScanId && response.length > 0) {
        setSelectedScanId(response[0].id);
      }
      if (selectedScanId && !response.find((scan) => scan.id === selectedScanId)) {
        setSelectedScanId(response[0]?.id ?? "");
      }
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load scans");
      return false;
    } finally {
      setLoadingScans(false);
      setRefreshingCounts(false);
    }
  }

  useEffect(() => {
    void loadScans(true, false);
  }, []);

  function updateRule(index: number, patch: Partial<ScanRule>) {
    setRules((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], ...patch };
      if (!next[index].compare_window) next[index].compare_window = null;
      return next;
    });
  }

  function addRule() {
    setRules((prev) => [...prev, emptyRule()]);
  }

  function removeRule(index: number) {
    setRules((prev) => {
      if (prev.length <= 1) return prev;
      return prev.filter((_, idx) => idx !== index);
    });
  }

  function resetBuilder() {
    setName("");
    setDescription("");
    setPositionFilter("");
    setRules([emptyRule()]);
    setPreviewResults([]);
  }

  async function createScan(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setStatus(null);

    try {
      await authRequest(
        "/scans",
        session,
        onSession,
        {
          method: "POST",
          json: {
            name,
            description,
            position_filter: positionFilter || null,
            alerts_enabled: false,
            rules: rules.map((rule) => ({
              ...rule,
              value: Number(rule.value),
              compare_window: rule.compare_window || null,
            })),
          },
        },
      );

      setStatus("Scan created.");
      resetBuilder();
      await loadScans(true, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create scan");
    } finally {
      setSaving(false);
    }
  }

  async function previewScan() {
    setPreviewing(true);
    setError(null);
    setStatus(null);

    try {
      const response = await publicRequest<Player[]>("/scans/preview?limit=25", {
        method: "POST",
        json: {
          name: name || "Preview",
          description,
          position_filter: positionFilter || null,
          rules: rules.map((rule) => ({
            ...rule,
            value: Number(rule.value),
            compare_window: rule.compare_window || null,
          })),
        },
      });
      setPreviewResults(response);
      setStatus(`Preview complete: ${response.length} players.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to preview scan");
    } finally {
      setPreviewing(false);
    }
  }

  async function evaluateScan(scanId: string) {
    setError(null);
    setStatus(null);
    try {
      const response = await publicRequest<Player[]>(`/scans/${scanId}/evaluate?limit=40`, {
        method: "POST",
      });
      setEvaluatedByScan((prev) => ({ ...prev, [scanId]: response }));
      setSelectedScanId(scanId);
      setStatus(`Evaluation complete: ${response.length} players returned.`);
      await loadScans(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to evaluate scan");
    }
  }

  async function refreshCounts(force: boolean) {
    setStatus(null);
    setError(null);
    const ok = await loadScans(true, force);
    if (ok) {
      setStatus(force ? "Scan counts fully refreshed." : "Scan counts refreshed for stale scans.");
    }
  }

  async function deleteScan(scanId: string) {
    setError(null);
    setStatus(null);
    try {
      await authRequest(`/scans/${scanId}`, session, onSession, {
        method: "DELETE",
      });
      if (selectedScanId === scanId) {
        setSelectedScanId("");
      }
      setEvaluatedByScan((prev) => {
        const next = { ...prev };
        delete next[scanId];
        return next;
      });
      await loadScans(false);
      setStatus("Scan deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete scan");
    }
  }

  async function togglePresetHidden(scan: Scan) {
    setError(null);
    try {
      await authRequest(
        `/scans/${scan.id}`,
        session,
        onSession,
        {
          method: "PUT",
          json: {
            is_hidden: !scan.is_hidden,
          },
        },
      );
      await loadScans(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update preset visibility");
    }
  }

  return (
    <div className="page-stack">
      <section className="card ios-card">
        <div className="list-head">
          <h2>Scans</h2>
          <small className="muted">{scans.length} total</small>
        </div>
        <p className="muted">Preset scans are auto-populated. Build custom scans and preview before saving.</p>
        <div className="button-row">
          <button onClick={() => void refreshCounts(false)} disabled={refreshingCounts}>
            {refreshingCounts ? "Refreshing..." : "Refresh Counts"}
          </button>
          <button className="primary" onClick={() => void refreshCounts(true)} disabled={refreshingCounts}>
            Force Recompute All
          </button>
        </div>
        {loadingScans ? <p className="muted">Loading scans...</p> : null}
      </section>

      <section className="card ios-card">
        <h3>Create Custom Scan</h3>
        <form className="scan-builder" onSubmit={createScan}>
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <label>
            Description
            <input value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <label>
            Position filter
            <select value={positionFilter} onChange={(event) => setPositionFilter(event.target.value)}>
              <option value="">All</option>
              <option value="C">C</option>
              <option value="LW">LW</option>
              <option value="RW">RW</option>
              <option value="D">D</option>
              <option value="G">G</option>
            </select>
          </label>

          <div className="rule-stack">
            <div className="list-head">
              <h3>Rules</h3>
              <button type="button" onClick={addRule}>
                Add Rule
              </button>
            </div>
            {rules.map((rule, index) => (
              <div key={index} className="rule-row">
                <label>
                  Stat
                  <select value={rule.stat} onChange={(event) => updateRule(index, { stat: event.target.value })}>
                    {STAT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Comparator
                  <select
                    value={rule.comparator}
                    onChange={(event) => updateRule(index, { comparator: event.target.value })}
                  >
                    {COMPARATOR_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Value
                  <input
                    type="number"
                    step="0.01"
                    value={rule.value}
                    onChange={(event) => updateRule(index, { value: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Window
                  <select value={rule.window} onChange={(event) => updateRule(index, { window: event.target.value })}>
                    {WINDOW_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Compare window
                  <select
                    value={rule.compare_window ?? ""}
                    onChange={(event) => updateRule(index, { compare_window: event.target.value || null })}
                  >
                    <option value="">None</option>
                    {WINDOW_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="button" className="danger" onClick={() => removeRule(index)}>
                  Remove
                </button>
              </div>
            ))}
          </div>

          <div className="button-row">
            <button type="button" onClick={() => void previewScan()} disabled={previewing}>
              {previewing ? "Previewing..." : "Preview"}
            </button>
            <button className="primary" type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save Scan"}
            </button>
          </div>
        </form>
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h3>My Scans</h3>
          <small className="muted">Tap evaluate to populate the result panel.</small>
        </div>
        <div className="scan-list">
          {scans.map((scan) => (
            <article
              key={scan.id}
              className={`scan-card ${selectedScanId === scan.id ? "active" : ""}`}
              onClick={() => setSelectedScanId(scan.id)}
            >
              <div className="list-head">
                <strong>{scan.name}</strong>
                <span className="badge">{scan.match_count} matches</span>
              </div>
              <p className="muted compact">{scan.description}</p>
              <div className="badge-row">
                <span className="badge">{scan.is_preset ? "Preset" : "Custom"}</span>
                {scan.position_filter ? <span className="badge">{scan.position_filter}</span> : null}
                {scan.is_hidden ? <span className="badge">Hidden</span> : null}
              </div>
              <ul className="simple-list">
                {scan.rules.map((rule) => (
                  <li key={rule.id ?? `${rule.stat}-${rule.window}-${rule.value}`}>{formatRule(rule)}</li>
                ))}
              </ul>
              <p className="muted compact">
                Last evaluated: {scan.last_evaluated ? new Date(scan.last_evaluated).toLocaleString() : "never"}
              </p>
              <div className="button-row">
                <button
                  onClick={(event) => {
                    event.stopPropagation();
                    void evaluateScan(scan.id);
                  }}
                >
                  Evaluate
                </button>
                {scan.is_preset ? (
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      void togglePresetHidden(scan);
                    }}
                  >
                    {scan.is_hidden ? "Unhide" : "Hide"}
                  </button>
                ) : (
                  <button
                    className="danger"
                    onClick={(event) => {
                      event.stopPropagation();
                      void deleteScan(scan.id);
                    }}
                  >
                    Delete
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h3>
            {selectedScan ? selectedScan.name : "Scan Results"}
          </h3>
          <small className="muted">{selectedResults.length} evaluated • {previewResults.length} preview</small>
        </div>
        {status ? <p className="success">{status}</p> : null}
        {error ? <p className="error">{error}</p> : null}

        {selectedScan ? (
          <div className="button-row">
            <button onClick={() => void evaluateScan(selectedScan.id)}>Evaluate Selected</button>
          </div>
        ) : null}

        {previewResults.length > 0 ? (
          <>
            <h3>Preview Results</h3>
            <div className="player-list">
              {previewResults.map((player) => {
                const score = Math.max(0, Math.min(100, Math.round(player.current_streamer_score)));
                const ringStyle: CSSProperties = {
                  background: `conic-gradient(${scoreColor(score)} ${score}%, rgba(255,255,255,0.14) 0)`,
                };
                return (
                  <Link key={player.id} to={`/players/${player.id}`} className="player-row">
                    <div className="avatar">{initials(player.name)}</div>
                    <div className="player-main">
                      <strong>{player.name}</strong>
                      <p className="muted compact">
                        {player.team} <span className="badge-pos">{player.position}</span> • {player.ownership_percentage.toFixed(1)}% owned
                      </p>
                    </div>
                    <div className="score-ring" style={ringStyle}>
                      <span>{score}</span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </>
        ) : null}

        {selectedResults.length > 0 ? (
          <>
            <h3>Evaluated Results</h3>
            <div className="player-list">
              {selectedResults.map((player) => {
                const score = Math.max(0, Math.min(100, Math.round(player.current_streamer_score)));
                const ringStyle: CSSProperties = {
                  background: `conic-gradient(${scoreColor(score)} ${score}%, rgba(255,255,255,0.14) 0)`,
                };
                return (
                  <Link key={player.id} to={`/players/${player.id}`} className="player-row">
                    <div className="avatar">{initials(player.name)}</div>
                    <div className="player-main">
                      <strong>{player.name}</strong>
                      <p className="muted compact">
                        {player.team} <span className="badge-pos">{player.position}</span> • {player.ownership_percentage.toFixed(1)}% owned
                      </p>
                    </div>
                    <div className="score-ring" style={ringStyle}>
                      <span>{score}</span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </>
        ) : (
          <p className="muted">Run preview or evaluate a scan to populate results.</p>
        )}
      </section>
    </div>
  );
}
