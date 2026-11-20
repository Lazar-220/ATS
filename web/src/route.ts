// Hash routes, so the browser's back button works and a screen can be bookmarked, with no
// router dependency. A route is a plain value; `parseRoute` and `href` are inverses.

export type Route =
  | { name: "positions" }
  | { name: "requirements"; positionId: string }
  | { name: "ranking"; positionId: string }
  | { name: "assessment"; positionId: string; assessmentId: string }
  | { name: "not-found" };

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, "").replace(/\/+$/, "");
  const parts = path === "" ? [] : path.split("/").map(decodeURIComponent);
  const [first, id, third, assessmentId] = parts;
  if (parts.length === 0) {
    return { name: "positions" };
  }
  if (first === "positions" && id) {
    if (parts.length === 2) {
      return { name: "requirements", positionId: id };
    }
    if (parts.length === 3 && third === "ranking") {
      return { name: "ranking", positionId: id };
    }
    if (parts.length === 4 && third === "assessments" && assessmentId) {
      return { name: "assessment", positionId: id, assessmentId };
    }
  }
  return { name: "not-found" };
}

export function href(route: Exclude<Route, { name: "not-found" }>): string {
  const enc = encodeURIComponent;
  switch (route.name) {
    case "positions":
      return "#/";
    case "requirements":
      return `#/positions/${enc(route.positionId)}`;
    case "ranking":
      return `#/positions/${enc(route.positionId)}/ranking`;
    case "assessment":
      return `#/positions/${enc(route.positionId)}/assessments/${enc(route.assessmentId)}`;
  }
}
