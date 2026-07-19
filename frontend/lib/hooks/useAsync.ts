"use client";

import { useEffect, useRef, useState, type DependencyList } from "react";

export type AsyncState<T> =
  | { status: "idle"; data: null; error: null }
  | { status: "loading"; data: null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: string };

interface Options {
  enabled?: boolean;
  retainSuccess?: boolean;
}

const initialState = { status: "idle", data: null, error: null } as const;

export function useAsync<T>(
  factory: () => Promise<T>,
  dependencies: DependencyList,
  { enabled = true, retainSuccess = false }: Options = {},
): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>(initialState);
  const requestGeneration = useRef(0);
  const hasSucceeded = useRef(false);

  useEffect(() => {
    hasSucceeded.current = false;
  }, dependencies); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!enabled || (retainSuccess && hasSucceeded.current)) return;

    const generation = ++requestGeneration.current;
    setState({ status: "loading", data: null, error: null });

    void factory().then(
      (data) => {
        if (requestGeneration.current !== generation) return;
        hasSucceeded.current = true;
        setState({ status: "success", data, error: null });
      },
      (error: unknown) => {
        if (requestGeneration.current !== generation) return;
        setState({
          status: "error",
          data: null,
          error: error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.",
        });
      },
    );

    return () => {
      if (requestGeneration.current === generation) requestGeneration.current += 1;
    };
  }, [enabled, factory, retainSuccess, ...dependencies]); // eslint-disable-line react-hooks/exhaustive-deps

  return state;
}
