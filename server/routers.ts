import { z } from "zod";
import { COOKIE_NAME } from "../shared/const.js";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, router } from "./_core/trpc";
import { getAllTheologians } from "../data/theologians";
import { invokeLLM } from "./_core/llm";

const chatMessageSchema = z.object({
  role: z.enum(["user", "assistant"]),
  content: z.string().trim().min(1).max(1200),
});

type FlowCoreTheologyResponse = {
  message: string;
  model?: string;
  provider?: string;
  source_count?: number;
  document_count?: number;
  memory_count?: number;
  recent_context_used?: boolean;
};

async function respondViaFlowCore(theologianSlug: string, messages: Array<{ role: "user" | "assistant"; content: string }>) {
  const baseUrl = process.env.FLOWCORE_BASE_URL?.replace(/\/$/, "");
  if (!baseUrl) return null;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = process.env.FLOWCORE_API_TOKEN;
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${baseUrl}/api/theology/respond`, {
    method: "POST",
    headers,
    body: JSON.stringify({ theologian_slug: theologianSlug, messages }),
    signal: AbortSignal.timeout(120_000),
  });
  const payload = (await response.json().catch(() => ({}))) as Partial<FlowCoreTheologyResponse> & { detail?: string };
  if (!response.ok) {
    throw new Error(payload.detail || "O FlowCore não conseguiu responder à pesquisa teológica.");
  }
  if (!payload.message) throw new Error("O FlowCore retornou uma resposta vazia.");
  return payload;
}

export const appRouter = router({
  system: systemRouter,
  auth: router({
    me: publicProcedure.query((opts) => opts.ctx.user),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return { success: true } as const;
    }),
  }),
  chat: router({
    respond: publicProcedure
      .input(z.object({ theologianSlug: z.string().min(1), messages: z.array(chatMessageSchema).min(1).max(30) }))
      .mutation(async ({ input }) => {
        const theologian = getAllTheologians().find((entry) => entry.slug === input.theologianSlug);
        if (!theologian) throw new Error("Teólogo não encontrado");

        const flowCoreResponse = await respondViaFlowCore(input.theologianSlug, input.messages);
        if (flowCoreResponse) {
          return {
            message: flowCoreResponse.message,
            model: flowCoreResponse.model,
            provider: flowCoreResponse.provider,
            sourceCount: flowCoreResponse.source_count ?? 0,
            documentCount: flowCoreResponse.document_count ?? 0,
            memoryCount: flowCoreResponse.memory_count ?? 0,
            recentContextUsed: flowCoreResponse.recent_context_used ?? false,
          };
        }

        const response = await invokeLLM({
          model: "gpt-5-mini",
          messages: [
            { role: "system", content: theologian.prompt },
            ...input.messages,
          ],
        });
        const content = response.choices?.[0]?.message?.content;
        const message = typeof content === "string" ? content.trim() : "";
        if (!message) throw new Error("O modelo não retornou conteúdo");
        return {
          message,
          sourceCount: 0,
          documentCount: 0,
          memoryCount: 0,
          recentContextUsed: false,
        };
      }),
  }),
});

export type AppRouter = typeof appRouter;
