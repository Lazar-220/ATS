import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";

import { fetchHealth } from "./api";
import { AssessmentScreen } from "./AssessmentScreen";
import { healthState } from "./health";
import { PositionEditor } from "./PositionEditor";
import { PositionsList } from "./PositionsList";
import { RankingScreen } from "./RankingScreen";
import { href, type Route } from "./route";
import { UploadForm, type UploadFormHandle } from "./Upload";
import { Breadcrumb, type Crumb } from "./ui/Breadcrumb";
import { TopBar } from "./ui/TopBar";
import { useRoute } from "./useRoute";

const POSITIONS = "Positions";

function crumbsFor(route: Route): Crumb[] {
  const home = { label: POSITIONS, href: href({ name: "positions" }) };
  switch (route.name) {
    case "positions":
      return [{ label: POSITIONS }];
    case "assessment":
      return [home, { label: "Ranked list", href: href({ name: "ranking", positionId: route.positionId }) }];
    default:
      return [home];
  }
}

export function App() {
  const route = useRoute();
  // "Add CVs" sits in the positions table and acts on the upload form above it.
  const uploadForm = useRef<UploadFormHandle>(null);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5000,
    retry: false,
  });

  return (
    <>
      <TopBar
        health={{
          state: healthState(health),
          api: health.data?.status,
          database: health.data?.database,
          message: health.error?.message,
        }}
      />
      <main className={route.name === "ranking" || route.name === "assessment" ? "page page--wide" : "page"}>
        <Breadcrumb items={crumbsFor(route)} />
        {route.name === "positions" && (
          <>
            <h1 className="sr-only">Positions</h1>
            <UploadForm ref={uploadForm} />
            <PositionsList onAddCvs={(position) => uploadForm.current?.addTo(position)} />
          </>
        )}
        {route.name === "requirements" && (
          <PositionEditor key={route.positionId} positionId={route.positionId} />
        )}
        {route.name === "ranking" && <RankingScreen positionId={route.positionId} />}
        {route.name === "assessment" && <AssessmentScreen assessmentId={route.assessmentId} />}
        {route.name === "not-found" && <p role="alert">There is no such page.</p>}
      </main>
    </>
  );
}
