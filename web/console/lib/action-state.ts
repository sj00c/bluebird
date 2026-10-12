export type ActionState = { error?: string; ok?: string };
export type FormAction = (
  state: ActionState,
  data: FormData,
) => Promise<ActionState>;
