"use client";

import { startTransition, useActionState } from "react";
import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";
import type { FormAction } from "@/lib/action-state";

export function Submit({
  children,
  className,
  pendingLabel = "저장 중…",
}: {
  children: ReactNode;
  className?: string;
  pendingLabel?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} className={className}>
      {pending ? pendingLabel : children}
    </button>
  );
}

export function ActionForm({
  action,
  children,
  className = "stack",
}: {
  action: FormAction;
  children: ReactNode;
  className?: string;
}) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form
      action={formAction}
      onSubmit={(event) => {
        event.preventDefault();
        // Capture before disabling the fieldset, and retain input on failure.
        const data = new FormData(event.currentTarget);
        startTransition(() => formAction(data));
      }}
      className={className}
      aria-busy={pending}
    >
      {state.error && (
        <div className="msg err" role="alert">
          {state.error}
        </div>
      )}
      {state.ok && (
        <div className="msg ok" role="status">
          {state.ok}
        </div>
      )}
      <fieldset disabled={pending}>{children}</fieldset>
      {pending && (
        <p className="muted" role="status">
          저장 중…
        </p>
      )}
    </form>
  );
}
