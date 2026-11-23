import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { sourceFiles } from "./sourceFiles.ts";

// CV text is untrusted (§4.4). React escapes text children, so the only way to turn a CV into
// markup is one of these APIs; none may appear in the app's source. The names are built from
// parts so this file does not match its own search.
const FORBIDDEN = [
  ["dangerously", "SetInnerHTML"],
  ["inner", "HTML"],
  ["outer", "HTML"],
  ["insertAdjacent", "HTML"],
  ["document", ".write"],
  ["create", "ContextualFragment"],
].map((parts) => parts.join(""));

test("no source file renders HTML from a string", () => {
  const dir = new URL(".", import.meta.url);
  const files = sourceFiles();
  assert.ok(files.length > 0);
  // Icons are drawn from JSX paths, so the icon file is the one a nested listing must not miss.
  assert.ok(files.includes("ui/Icon.tsx"), "files in subfolders are scanned");
  for (const name of files) {
    const source = readFileSync(new URL(name, dir), "utf8");
    for (const word of FORBIDDEN) {
      assert.ok(!source.includes(word), `${name} uses ${word}`);
    }
  }
});
