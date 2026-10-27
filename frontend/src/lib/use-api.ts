"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

export type ApiState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (updater: (prev: T | null) => T | null) => void;
};

/** Tải dữ liệu một lần khi mount (và khi gọi `reload`). Không dùng thư viện cache để giữ app nhẹ. */
export function useApi<T>(loader: () => Promise<T>): ApiState<T> {
  const [data, setDataState] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDataState(await loaderRef.current());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const setData = useCallback((updater: (prev: T | null) => T | null) => setDataState(updater), []);
  return { data, error, loading, reload, setData };
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Đã có lỗi xảy ra.";
}
