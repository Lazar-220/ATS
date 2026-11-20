import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchHealth } from "./api";
import { AssessmentScreen } from "./AssessmentScreen";
import { PositionEditor } from "./PositionEditor";
import { PositionsList } from "./PositionsList";
import { RankingScreen } from "./RankingScreen";
import { UploadForm } from "./Upload";

type View =
  | { name: "positions" }
  | { name: "requirements"; positionId: string }
  | { name: "ranking"; positionId: string }
  | { name: "assessment"; positionId: string; assessmentId: string };

export function App() {
  const [view, setView] = useState<View>({ name: "positions" });
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
      {view.name === "positions" && (
        <>
          <UploadForm onOpenRanking={(positionId) => setView({ name: "ranking", positionId })} />
          <h2>Positions</h2>
          <PositionsList
            onOpen={(positionId) => setView({ name: "requirements", positionId })}
            onOpenRanking={(positionId) => setView({ name: "ranking", positionId })}
          />
        </>
      )}
      {view.name === "requirements" && (
        <PositionEditor
          positionId={view.positionId}
          onBack={() => setView({ name: "positions" })}
        />
      )}
      {view.name === "ranking" && (
        <>
          <p>
            <button type="button" onClick={() => setView({ name: "positions" })}>
              ← Positions
            </button>
          </p>
          <RankingScreen
            positionId={view.positionId}
            onOpenAssessment={(assessmentId) =>
              setView({ name: "assessment", positionId: view.positionId, assessmentId })
            }
          />
        </>
      )}
      {view.name === "assessment" && (
        <>
          <p>
            <button
              type="button"
              onClick={() => setView({ name: "ranking", positionId: view.positionId })}
            >
              ← Ranked list
            </button>
          </p>
          <AssessmentScreen assessmentId={view.assessmentId} />
        </>
      )}
    </main>
  );
}
