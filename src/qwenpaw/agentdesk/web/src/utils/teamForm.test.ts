import { describe, expect, it } from "vitest";

import {
  countTeamWorkers,
  normalizeTeamWorkers,
  splitTeamRoster,
} from "./teamForm";

describe("splitTeamRoster", () => {
  it("splits explicit leader from workers", () => {
    expect(
      splitTeamRoster({
        leader: "PM",
        members: ["Dev", "QA"],
      }),
    ).toEqual({ leader: "PM", workers: ["Dev", "QA"] });
  });

  it("migrates legacy leader-first members", () => {
    expect(
      splitTeamRoster({
        leader: "Analyst",
        members: ["Analyst", "Writer"],
      }),
    ).toEqual({ leader: "Analyst", workers: ["Writer"] });
  });

  it("infers leader from first member when leader field is empty", () => {
    expect(
      splitTeamRoster({
        members: ["Lead", "Worker"],
      }),
    ).toEqual({ leader: "Lead", workers: ["Worker"] });
  });
});

describe("normalizeTeamWorkers", () => {
  it("removes leader from worker list", () => {
    expect(normalizeTeamWorkers("PM", ["Dev", "PM", "QA"])).toEqual([
      "Dev",
      "QA",
    ]);
  });
});

describe("countTeamWorkers", () => {
  it("counts workers excluding leader", () => {
    expect(
      countTeamWorkers({
        leader: "PM",
        members: ["Dev", "QA"],
      }),
    ).toBe(2);
    expect(
      countTeamWorkers({
        leader: "PM",
        members: ["PM", "Dev", "QA"],
      }),
    ).toBe(2);
  });
});
