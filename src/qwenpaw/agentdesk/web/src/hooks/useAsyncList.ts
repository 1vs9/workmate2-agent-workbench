import { useCallback, useEffect, useRef, useState } from "react";

interface AsyncListState<T> {
  data: T[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  reload: () => void;
  setData: React.Dispatch<React.SetStateAction<T[]>>;
}

/**
 * Load a list from an async loader on mount, exposing loading/error state and a
 * manual reload. The loader identity controls re-fetching, so memoize it.
 */
export function useAsyncList<T>(loader: () => Promise<T[]>): AsyncListState<T> {
  const [data, setData] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initialLoadedRef = useRef(false);
  const requestIdRef = useRef(0);

  const reload = useCallback(() => {
    const requestId = ++requestIdRef.current;
    let cancelled = false;
    const initial = !initialLoadedRef.current;
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);
    loader()
      .then((items) => {
        if (cancelled || requestId !== requestIdRef.current) return;
        setData(Array.isArray(items) ? items : []);
      })
      .catch((err: unknown) => {
        if (cancelled || requestId !== requestIdRef.current) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (cancelled || requestId !== requestIdRef.current) return;
        initialLoadedRef.current = true;
        setLoading(false);
        setRefreshing(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loader]);

  useEffect(() => {
    const cleanup = reload();
    return cleanup;
  }, [reload]);

  return { data, loading, refreshing, error, reload, setData };
}
