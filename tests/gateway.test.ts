import { describe, expect, it } from "vitest";
import { PUBLIC_GATEWAY_URL, resolveGatewayUrl } from "../constants/gateway";

describe("resolveGatewayUrl", () => {
  it("usa o gateway público quando o ambiente EAS não definiu uma URL", () => {
    expect(resolveGatewayUrl(undefined)).toBe(PUBLIC_GATEWAY_URL);
    expect(resolveGatewayUrl("   ")).toBe(PUBLIC_GATEWAY_URL);
  });

  it("preserva uma URL fornecida pelo ambiente sem barra final", () => {
    expect(resolveGatewayUrl("https://api.exemplo.test/")).toBe("https://api.exemplo.test");
  });
});
