import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchHealth } from "./api";
import { PositionEditor } from "./PositionEditor";
import { PositionsList } from "./PositionsList";
import { UploadForm } from "./Upload";

export function App() {
  const [positionId, setPositionId] = useState<string | null>(null);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5000,
    retry: false,
  });

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", margin: "2rem auto", maxWidth: "64rem" }}>
      <h1>ATS</h1>
      <p style={{ color: "#555" }}>
        {health.isPending && "Checking the API…"}
        {health.isError && <span data-testid="health">API unreachable: {health.error.message}</span>}
        {health.data && (
          <span data-testid="health">
            API: <strong>{health.data.status}</strong>, database:{" "}
            <strong>{health.data.database}</strong>
          </span>
        )}
      </p>
      {positionId === null ? (
        <>
          <UploadForm onOpenRanking={setPositionId} />
          <h2>Positions</h2>
          <PositionsList onOpen={setPositionId} />
        </>
      ) : (
        <PositionEditor positionId={positionId} onBack={() => setPositionId(null)} />
      )}
    </main>
  );
}
