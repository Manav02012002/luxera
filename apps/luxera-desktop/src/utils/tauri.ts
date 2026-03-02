export function hasTauriRuntime(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

interface TauriDialogOptions {
  title?: string;
  defaultPath?: string;
  directory?: boolean;
  multiple?: boolean;
  filters?: Array<{ name: string; extensions: string[] }>;
}

type TauriDialogResult = string | string[] | null;

export async function tauriInvoke<T>(cmd: string, args: Record<string, unknown>): Promise<T> {
  const tauri = (window as Window & { __TAURI__?: { core?: { invoke?: (c: string, a: unknown) => Promise<unknown> } } })
    .__TAURI__;
  const invokeFn = tauri?.core?.invoke;
  if (!invokeFn) {
    throw new Error("Tauri runtime API unavailable.");
  }
  return (await invokeFn(cmd, args)) as T;
}

export async function tauriDialogOpen(options: TauriDialogOptions): Promise<TauriDialogResult> {
  const tauri = (window as Window & {
    __TAURI__?: { dialog?: { open?: (opts: TauriDialogOptions) => Promise<TauriDialogResult> } };
  }).__TAURI__;
  const openFn = tauri?.dialog?.open;
  if (!openFn) {
    throw new Error("Tauri dialog plugin unavailable.");
  }
  return openFn(options);
}

export async function tauriDialogSave(options: TauriDialogOptions): Promise<string | null> {
  const tauri = (window as Window & {
    __TAURI__?: { dialog?: { save?: (opts: TauriDialogOptions) => Promise<string | null> } };
  }).__TAURI__;
  const saveFn = tauri?.dialog?.save;
  if (!saveFn) {
    throw new Error("Tauri dialog plugin unavailable.");
  }
  return saveFn(options);
}
