"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { api, ApiError, type ResearchJob, type ResearchReport } from "@/lib/api";

const POLL_INTERVAL_MS = 5_000;
const MAX_POLL_MS = 15 * 60 * 1_000;

export type DeepResearchState =
  | { phase: "loading" }
  | { phase: "generating"; job: ResearchJob | null; startedAt: number }
  | { phase: "has_report"; report: ResearchReport }
  | { phase: "error"; message: string };

type Action =
  | { type: "load" }
  | { type: "generate"; startedAt: number }
  | { type: "job"; job: ResearchJob }
  | { type: "report"; report: ResearchReport }
  | { type: "error"; message: string };

function reducer(state: DeepResearchState, action: Action): DeepResearchState {
  switch (action.type) {
    case "load":
      return { phase: "loading" };
    case "generate":
      return { phase: "generating", job: null, startedAt: action.startedAt };
    case "job":
      return state.phase === "generating" ? { ...state, job: action.job } : state;
    case "report":
      return { phase: "has_report", report: action.report };
    case "error":
      return { phase: "error", message: action.message };
  }
}

export function useDeepResearch(symbol: string) {
  const [state, dispatch] = useReducer(reducer, { phase: "loading" });
  const requestGeneration = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearPoll = useCallback(() => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const isCurrent = useCallback(
    (generation: number) => requestGeneration.current === generation,
    [],
  );

  const loadLatest = useCallback(async (generation: number) => {
    const report = await api.research.get(symbol);
    if (isCurrent(generation)) dispatch({ type: "report", report });
  }, [isCurrent, symbol]);

  const poll = useCallback(async function pollJob(
    jobId: number,
    startedAt: number,
    generation: number,
  ): Promise<void> {
    if (!isCurrent(generation)) return;
    if (Date.now() - startedAt > MAX_POLL_MS) {
      dispatch({
        type: "error",
        message: "리포트 생성이 시간 내에 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.",
      });
      return;
    }

    try {
      const job = await api.research.getJob(jobId);
      if (!isCurrent(generation)) return;
      dispatch({ type: "job", job });

      if (job.status === "completed") {
        await loadLatest(generation);
        return;
      }
      if (job.status === "failed") {
        dispatch({ type: "error", message: job.error || "리포트 생성에 실패했습니다." });
        return;
      }
      timeoutRef.current = setTimeout(
        () => void pollJob(jobId, startedAt, generation),
        POLL_INTERVAL_MS,
      );
    } catch (error: unknown) {
      if (!isCurrent(generation)) return;
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "진행 상태를 확인하지 못했습니다.",
      });
    }
  }, [isCurrent, loadLatest]);

  const generate = useCallback(async (force = false) => {
    clearPoll();
    const generation = ++requestGeneration.current;
    const startedAt = Date.now();
    dispatch({ type: "generate", startedAt });

    try {
      const job = await api.research.create(symbol, { force });
      if (!isCurrent(generation)) return;
      if (job.cached || (job.status === "completed" && job.report)) {
        await loadLatest(generation);
        return;
      }
      dispatch({ type: "job", job });
      timeoutRef.current = setTimeout(
        () => void poll(job.job_id, startedAt, generation),
        POLL_INTERVAL_MS,
      );
    } catch (error: unknown) {
      if (!isCurrent(generation)) return;
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "리포트 생성을 시작하지 못했습니다.",
      });
    }
  }, [clearPoll, isCurrent, loadLatest, poll, symbol]);

  useEffect(() => {
    clearPoll();
    const generation = ++requestGeneration.current;
    dispatch({ type: "load" });

    void loadLatest(generation).catch((error: unknown) => {
      if (!isCurrent(generation)) return;
      if (error instanceof ApiError && error.status === 404) {
        void generate();
        return;
      }
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "리포트를 불러오지 못했습니다.",
      });
    });

    return () => {
      requestGeneration.current += 1;
      clearPoll();
    };
  }, [clearPoll, generate, isCurrent, loadLatest, symbol]);

  return {
    state,
    retry: () => void generate(),
    regenerate: () => void generate(true),
  };
}
