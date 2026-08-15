import { z } from "zod";
import { COOKIE_NAME } from "../shared/const.js";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, router } from "./_core/trpc";
import { getAllTheologians } from "../data/theologians";

const chatMessageSchema = z.object({
  role: z.enum(["user", "assistant"]),
  content: z.string().trim().min(1).max(1200),
});

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
        const apiKey = process.env.OPENAI_API_KEY;
        if (!apiKey) throw new Error("OPENAI_API_KEY não configurada no servidor");

        const response = await fetch("https://api.openai.com/v1/chat/completions", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
          body: JSON.stringify({
            model: process.env.OPENAI_MODEL || "gpt-4o-mini",
            temperature: 0.75,
            max_tokens: 700,
            messages: [
              { role: "system", content: theologian.prompt },
              ...input.messages,
            ],
          }),
        });
        if (!response.ok) {
          const details = await response.text();
          console.error("OpenAI request failed", response.status, details.slice(0, 500));
          throw new Error("Falha ao consultar a OpenAI");
        }
        const data = (await response.json()) as { choices?: Array<{ message?: { content?: string } }> };
        const message = data.choices?.[0]?.message?.content?.trim();
        if (!message) throw new Error("A OpenAI não retornou conteúdo");
        return { message };
      }),
  }),
});

export type AppRouter = typeof appRouter;
