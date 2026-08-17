import { createTRPCReact } from "@trpc/react-query";
import { httpBatchLink } from "@trpc/client";
import superjson from "superjson";
import type { AppRouter } from "@/server/routers";
import { getApiBaseUrl } from "@/constants/oauth";
import * as Auth from "@/lib/_core/auth";

/**
 * tRPC React client for type-safe API calls.
 *
 * IMPORTANT (tRPC v11): The `transformer` must be inside `httpBatchLink`,
 * NOT at the root createClient level. This ensures client and server
 * use the same serialization format (superjson).
 */
export const trpc = createTRPCReact<AppRouter>();

/**
 * Creates the tRPC client with proper configuration.
 * Call this once in your app's root layout.
 */
export function createTRPCClient() {
  return trpc.createClient({
    links: [
      httpBatchLink({
        // Keep this relative so the custom fetch can resolve the runtime host
        // selected in the installed APK after the client was created.
        url: "/api/trpc",
        // tRPC v11: transformer MUST be inside httpBatchLink, not at root
        transformer: superjson,
        async headers() {
          const token = await Auth.getSessionToken();
          return token ? { Authorization: `Bearer ${token}` } : {};
        },
        // The public chat gateway does not require a user session. Omitting
        // credentials keeps browser builds compatible with a permissive CORS
        // policy while Android requests remain unchanged.
        fetch(url, options) {
          const rawUrl = String(url);
          const baseUrl = getApiBaseUrl();
          const relativePath = rawUrl.replace(/^https?:\/\/[^/]+/i, "");
          const targetUrl = baseUrl
            ? `${baseUrl}${relativePath.startsWith("/") ? relativePath : `/${relativePath}`}`
            : rawUrl;
          return fetch(targetUrl, {
            ...options,
            credentials: "omit",
          });
        },
      }),
    ],
  });
}
