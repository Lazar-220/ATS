import { useQuery } from "@tanstack/react-query";

import { fetchPositions } from "./api";
import { ErrorNotice } from "./ui/Notice";
import { Loading } from "./ui/Loading";
import { href } from "./route";

const SETUP_LABEL = {
  pending: "waiting for the posting text",
  running: "extracting requirements…",
  done: "",
  failed: "failed",
} as const;

export function PositionsList() {
  const positions = useQuery({
    queryKey: ["positions"],
    queryFn: fetchPositions,
    refetchInterval: 5000,
  });

  if (positions.isPending) {
    return <Loading />;
  }
  if (positions.isError) {
    return <ErrorNotice message={positions.error.message} onRetry={() => void positions.refetch()} />;
  }
  if (positions.data.length === 0) {
    return <p>No positions yet. Upload a posting and CVs above to create one.</p>;
  }
  return (
    <table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead>
        <tr>
          {["Posting", "Rubric", "Version", "Requirements", ""].map((title) => (
            <th key={title} style={{ textAlign: "left", padding: "0.25rem" }}>
              {title}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {positions.data.map((position) => (
          <tr key={position.id}>
            <td style={{ padding: "0.25rem" }}>{position.filename ?? position.id}</td>
            <td style={{ padding: "0.25rem" }}>{position.rubric_status}</td>
            <td style={{ padding: "0.25rem" }}>{position.rubric_version}</td>
            <td style={{ padding: "0.25rem" }}>
              {position.setup_status === "done"
                ? position.requirement_count
                : SETUP_LABEL[position.setup_status]}
            </td>
            <td style={{ padding: "0.25rem" }}>
              <a href={href({ name: "requirements", positionId: position.id })}>Requirements</a>{" "}
              <a href={href({ name: "ranking", positionId: position.id })}>Ranked list</a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
