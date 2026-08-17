import type { Href } from "expo-router";

export function getPeriodRoute(periodId: string | string[] | undefined): Href {
  const normalizedPeriodId = Array.isArray(periodId) ? periodId[0] : periodId;
  if (!normalizedPeriodId) {
    return "/";
  }

  return {
    pathname: "/period/[id]",
    params: { id: normalizedPeriodId },
  };
}
