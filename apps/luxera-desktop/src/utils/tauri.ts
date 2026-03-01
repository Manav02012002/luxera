export function hasTauriRuntime(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

export async function tauriInvoke<T>(cmd: string, args: Record<string, unknown>): Promise<T> {
  const tauri = (window as Window & { __TAURI__?: { core?: { invoke?: (c: string, a: unknown) => Promise<unknown> } } })
    .__TAURI__;
  const invokeFn = tauri?.core?.invoke;
  if (!invokeFn) {
    throw new Error("Tauri runtime API unavailable.");
  }
  return (await invokeFn(cmd, args)) as T;
}
