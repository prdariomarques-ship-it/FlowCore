export const PUBLIC_GATEWAY_URL = "https://teologoschat-meectvnb.manus.space";

/**
 * Mantém a URL configurável pelos ambientes EAS, sem deixar builds nativos
 * sem um destino público quando a variável não estiver cadastrada.
 */
export function resolveGatewayUrl(value: unknown): string {
  return typeof value === "string" && value.trim()
    ? value.trim().replace(/\/$/, "")
    : PUBLIC_GATEWAY_URL;
}
