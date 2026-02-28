import { FormEvent, useState } from "react";

import { login } from "../api";
import type { AuthSession } from "../types";

type LoginPageProps = {
  onLogin: (session: AuthSession) => void;
};

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const session = await login(username, password);
      onLogin(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="app-shell boot-shell">
      <header className="top-header">
        <small className="eyebrow">Forecheck v2</small>
        <h1>Login</h1>
        <p className="muted">Single-owner local auth.</p>
      </header>
      <section className="card ios-card">
        <h2>Sign In</h2>

        <form onSubmit={onSubmit}>
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} required />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {error ? <p className="error">{error}</p> : null}

          <button className="primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </section>
    </main>
  );
}
