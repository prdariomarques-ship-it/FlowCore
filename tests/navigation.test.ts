import { describe, expect, it } from "vitest";
import { getPeriodRoute } from "../lib/navigation";

describe("getPeriodRoute", () => {
  it("returns the explicit source period route", () => {
    expect(getPeriodRoute("pre-reforma")).toEqual({
      pathname: "/period/[id]",
      params: { id: "pre-reforma" },
    });
  });

  it("uses the first Expo route parameter when it is an array", () => {
    expect(getPeriodRoute(["reforma", "ignorado"])).toEqual({
      pathname: "/period/[id]",
      params: { id: "reforma" },
    });
  });

  it("falls back to the library when no period is available", () => {
    expect(getPeriodRoute(undefined)).toBe("/");
  });
});
