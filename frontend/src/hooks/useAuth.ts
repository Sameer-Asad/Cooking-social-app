import { useCallback, useEffect, useState } from "react";
import { ApiError, authApi, type User } from "../api/client";

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    authApi
      .me()
      .then((user) => setState({ user, loading: false, error: null }))
      .catch(() => setState({ user: null, loading: false, error: null }));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setState((s) => ({ ...s, error: null }));
    try {
      const user = await authApi.login(email, password);
      setState({ user, loading: false, error: null });
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Something went wrong";
      setState((s) => ({ ...s, error: message }));
      throw e;
    }
  }, []);

  const signup = useCallback(async (email: string, password: string, username?: string) => {
    setState((s) => ({ ...s, error: null }));
    try {
      const user = await authApi.signup(email, password, username);
      setState({ user, loading: false, error: null });
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Something went wrong";
      setState((s) => ({ ...s, error: message }));
      throw e;
    }
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setState({ user: null, loading: false, error: null });
  }, []);

  const setUsername = useCallback(async (username: string) => {
    const user = await authApi.setUsername(username);
    setState((s) => ({ ...s, user }));
  }, []);

  return { ...state, login, signup, logout, setUsername };
}