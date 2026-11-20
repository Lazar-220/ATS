import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "./api";
import { AssessmentScreen } from "./AssessmentScreen";
import { PositionEditor } from "./PositionEditor";
import { PositionsList } from "./PositionsList";
import { RankingScreen } from "./RankingScreen";
import { href } from "./route";
import { UploadForm } from "./Upload";
import { useRoute } from "./useRoute";

function Breadcrumb({ items }: { items: { label: string; to: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" style={{ marginBottom: "1rem" }}>
      {items.map((item, index) => (
        <span key={item.to}>
          {index > 0 && " › "}
          <a href={item.to}>{item.label}</a>
        </span>
      ))}
    </nav>
  );
}

export function App() {
  const route = useRoute();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5000,
    retry: false,
  });
  const home = { label: "Positions", to: href({ name: "positions" }) };

  return (
    <main
      style={{
        fontFamily: "system-ui, sans-serif",
        margin: "2rem auto",
        maxWidth: "72rem",
        padding: "0 1rem",
      }}
    >
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
      {route.name === "positions" && (
        <>
          <UploadForm />
          <h2>Positions</h2>
          <PositionsList />
        </>
      )}
      {route.name === "requirements" && (
        <>
          <Breadcrumb items={[home]} />
          <PositionEditor positionId={route.positionId} />
        </>
      )}
      {route.name === "ranking" && (
        <>
          <Breadcrumb items={[home]} />
          <RankingScreen positionId={route.positionId} />
        </>
      )}
      {route.name === "assessment" && (
        <>
          <Breadcrumb
            items={[
              home,
              { label: "Ranked list", to: href({ name: "ranking", positionId: route.positionId }) },
            ]}
          />
          <AssessmentScreen assessmentId={route.assessmentId} />
        </>
      )}
      {route.name === "not-found" && (
        <>
          <p role="alert">There is no such page.</p>
          <Breadcrumb items={[home]} />
        </>
      )}
    </main>
  );
}
