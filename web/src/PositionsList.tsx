import { useQuery } from "@tanstack/react-query";

import { fetchPositions } from "./api";

const SETUP_LABEL = {
  pending: "waiting for the posting text",
  running: "extracting requirements…",
  done: "",
  failed: "failed",
} as const;

export function PositionsList({
  onOpen,
  onOpenRanking,
}: {
  onOpen: (id: string) => void;
  onOpenRanking: (id: string) => void;
}) {
  const positions = useQuery({
    queryKey: ["positions"],
    queryFn: fetchPositions,
    refetchInterval: 5000,
  });

  if (positions.isPending) {
    return <p>Loading…</p>;
  }
  if (positions.isError) {
    return <p role="alert">{positions.error.message}</p>;
  }
  if (positions.data.length === 0) {
    return <p>No positions yet. Upload a posting with POST /rankings.</p>;
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
              <button type="button" onClick={() => onOpen(position.id)}>
                Requirements
              </button>{" "}
              <button type="button" onClick={() => onOpenRanking(position.id)}>
                Ranked list
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
