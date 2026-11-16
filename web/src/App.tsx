import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "./api";

export function App() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5000,
    retry: false,
  });

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", margin: "2rem auto", maxWidth: "32rem" }}>
      <h1>ATS</h1>
      <h2>API health</h2>
      {health.isPending && <p>Checking…</p>}
      {health.isError && (
        <p data-testid="health">API unreachable: {health.error.message}</p>
      )}
      {health.data && (
        <p data-testid="health">
          API: <strong>{health.data.status}</strong>, database:{" "}
          <strong>{health.data.database}</strong>
        </p>
      )}
    </main>
  );
}
