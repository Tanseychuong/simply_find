import { useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { safeNext } from "../../components/guards";
import { useAuth } from "../../context/AuthContext";

/**
 * Handles an answer from login/, google/, mfa/login/, register/ or claim/:
 * `{user}` -> signed in, go to ?next= (or `fallback`);
 * `{mfa_required, mfa_token}` -> returns the token so the page asks for a code.
 */
export function useFinishSignIn(fallback = "/") {
  const { signedInAs } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  return useCallback(
    (data, nextFallback = fallback) => {
      if (data?.mfa_required) return { mfaToken: data.mfa_token };
      signedInAs(data.user);
      navigate(safeNext(params.get("next"), nextFallback), { replace: true });
      return null;
    },
    [signedInAs, navigate, params, fallback],
  );
}
