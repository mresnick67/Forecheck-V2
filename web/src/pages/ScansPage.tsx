import { FormEvent, useEffect, useState } from "react";

import { authRequest, publicRequest } from "../api";
import type { AuthSession, Player, Scan } from "../types";

type ScansPageProps = {
  session: AuthSession;
  onSession: (session: AuthSession | null) => void;
};

export default function ScansPage({ session, onSession }: ScansPageProps) {
  const [scans, setScans] = useState<Scan[]>([]);
  const [selectedScanId, setSelectedScanId] = useState<string>("");
  const [results, setResults] = useState<Player[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [stat, setStat] = useState("points");
  const [comparator, setComparator] = useState(">=");
  const [value, setValue] = useState("1");
  const [window, setWindow] = useState("L5");
  const [error, setError] = useState<string | null>(null);

  async function loadScans() {
    try {
      const response = await authRequest<Scan[]>("/scans?include_hidden=true", session, onSession);
      setScans(response);
      if (!selectedScanId && response.length > 0) {
        setSelectedScanId(response[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load scans");
    }
  }

  useEffect(() => {
    void loadScans();
  }, []);

  async function createScan(event: FormEvent) {
    event.preventDefault();
    setError(null);

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
            alerts_enabled: false,
            rules: [
              {
                stat,
                comparator,
                value: Number(value),
                window,
              },
            ],
          },
        },
      );

      setName("");
      setDescription("");
      await loadScans();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create scan");
    }
  }

  async function evaluateScan(scanId: string) {
    setError(null);
    try {
      const response = await publicRequest<Player[]>(`/scans/${scanId}/evaluate?limit=20`, {
        method: "POST",
      });
      setResults(response);
      setSelectedScanId(scanId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to evaluate scan");
    }
  }

  async function deleteScan(scanId: string) {
    setError(null);
    try {
      await authRequest(`/scans/${scanId}`, session, onSession, {
        method: "DELETE",
      });
      setResults([]);
      await loadScans();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete scan");
    }
  }

  return (
    <div className="grid cols-2">
      <section className="card">
        <h2>Create Scan</h2>
        <form onSubmit={createScan}>
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>

          <label>
            Description
            <input value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>

          <label>
            Stat
            <select value={stat} onChange={(event) => setStat(event.target.value)}>
              <option value="points">points</option>
              <option value="shots">shots</option>
              <option value="hits">hits</option>
              <option value="blocks">blocks</option>
              <option value="power_play_points">power_play_points</option>
              <option value="streamer_score">streamer_score</option>
            </select>
          </label>

          <label>
            Comparator
            <select value={comparator} onChange={(event) => setComparator(event.target.value)}>
              <option value=">=">&gt;=</option>
              <option value=">">&gt;</option>
              <option value="<=">&lt;=</option>
              <option value="<">&lt;</option>
              <option value="=">=</option>
            </select>
          </label>

          <label>
            Value
            <input value={value} onChange={(event) => setValue(event.target.value)} required />
          </label>

          <label>
            Window
            <select value={window} onChange={(event) => setWindow(event.target.value)}>
              <option value="L5">L5</option>
              <option value="L10">L10</option>
              <option value="L20">L20</option>
              <option value="Season">Season</option>
            </select>
          </label>

          <button className="primary" type="submit">
            Save Scan
          </button>
        </form>
      </section>

      <section className="card">
        <h2>My Scans</h2>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Matches</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {scans.map((scan) => (
              <tr key={scan.id}>
                <td>{scan.name}</td>
                <td>{scan.match_count}</td>
                <td>
                  <button onClick={() => void evaluateScan(scan.id)}>Evaluate</button>{" "}
                  {!scan.is_preset ? (
                    <button className="danger" onClick={() => void deleteScan(scan.id)}>
                      Delete
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card" style={{ gridColumn: "1 / -1" }}>
        <h2>Scan Results {selectedScanId ? `(${selectedScanId.slice(0, 8)})` : ""}</h2>
        {results.length === 0 ? <p className="muted">Run an evaluation to view matches.</p> : null}
        <ul>
          {results.map((player) => (
            <li key={player.id}>
              {player.name} ({player.team} {player.position}) - streamer {player.current_streamer_score.toFixed(1)}
            </li>
          ))}
        </ul>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
