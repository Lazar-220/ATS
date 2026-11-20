import assert from "node:assert/strict";
import { test } from "node:test";

import { href, parseRoute, type Route } from "./route.ts";

test("every route survives a round trip through its link", () => {
  const routes: Exclude<Route, { name: "not-found" }>[] = [
    { name: "positions" },
    { name: "requirements", positionId: "p1" },
    { name: "ranking", positionId: "p1" },
    { name: "assessment", positionId: "p1", assessmentId: "a1" },
  ];
  for (const route of routes) {
    assert.deepEqual(parseRoute(href(route)), route);
  }
});

test("the empty hash is the positions screen, and a trailing slash is ignored", () => {
  assert.deepEqual(parseRoute(""), { name: "positions" });
  assert.deepEqual(parseRoute("#/positions/p1/ranking/"), { name: "ranking", positionId: "p1" });
});

test("unknown or incomplete paths are not found", () => {
  for (const hash of ["#/nope", "#/positions", "#/positions/p1/x", "#/positions/p1/assessments"]) {
    assert.deepEqual(parseRoute(hash), { name: "not-found" }, hash);
  }
});

test("an id with a slash or markup is carried as data, not interpreted", () => {
  const route = { name: "requirements", positionId: "a/b<script>" } as const;
  assert.deepEqual(parseRoute(href(route)), route);
});
