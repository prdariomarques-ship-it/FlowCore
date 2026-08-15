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
        return { message };
      }),
  }),
});

export type AppRouter = typeof appRouter;
