import { readdirSync } from "node:fs";

// The app's own sources under src, nested folders included, without generated types and tests.
// Paths come back with "\" on Windows and "/" elsewhere, so they are normalised to "/" first and
// the names are matched by basename and extension.
export function sourceFiles(): string[] {
  const dir = new URL(".", import.meta.url);
  return readdirSync(dir, { recursive: true, encoding: "utf8" })
    .map((path) => path.split("\\").join("/"))
    .filter((path) => {
      const name = path.split("/").pop() ?? "";
      return /\.(ts|tsx)$/.test(name) && name !== "api-types.ts" && !name.endsWith(".test.ts");
    });
}
