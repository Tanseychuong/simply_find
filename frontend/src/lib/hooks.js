import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Load data on mount and whenever `deps` change; aborts the previous
 * request so a slow answer can't overwrite a newer one.
 *
 *   const { data, error, loading, reload, setData } = useApi((signal) => api.get(..., { signal }), [id]);
 */
export function useApi(loader, deps) {
  const [state, setState] = useState({ data: undefined, error: null, loading: true });
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    Promise.resolve(loaderRef.current(controller.signal))
      .then((data) => !controller.signal.aborted && setState({ data, error: null, loading: false }))
      .catch((error) => {
        if (controller.signal.aborted || error?.code === "ERR_CANCELED") return;
        setState((s) => ({ ...s, error, loading: false }));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((update) => setState((s) => ({ ...s, data: typeof update === "function" ? update(s.data) : update })), []);
  return { ...state, reload, setData };
}

/** Sets the browser tab title; "SimplyFind" alone on the home page. */
export function useTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} | SimplyFind` : "SimplyFind: internships and graduate roles";
  }, [title]);
}

export function useDebounced(value, ms = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}
