import { FormEvent, useState } from "react";

import { bootstrapOwner } from "../api";

type SetupPageProps = {
  onComplete: () => Promise<void>;
};

export default function SetupPage({ onComplete }: SetupPageProps) {
  const [username, setUsername] = useState("owner");
  const [email, setEmail] = useState("owner@local");
  const [displayName, setDisplayName] = useState("Owner");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      await bootstrapOwner({
        username,
        email,
        password,
        display_name: displayName,
      });
      await onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to bootstrap owner");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="layout">
      <section className="card">
        <h1>Forecheck v2 Setup</h1>
        <p className="muted">
          First-run setup creates the single local owner account.
        </p>

        <form onSubmit={onSubmit}>
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} required />
          </label>

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>

          <label>
            Display name
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              required
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={8}
              required
            />
          </label>

          {error ? <p className="error">{error}</p> : null}

          <button className="primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating owner..." : "Create Owner"}
          </button>
        </form>
      </section>
    </main>
  );
}
