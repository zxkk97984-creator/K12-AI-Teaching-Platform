import { completeInteractive, saveInteractive, viewedInteractive, type InteractiveSession } from "./api";

export type ActivityPatch = {
  scene_id?: string | null; game_state?: Record<string, unknown> | null;
  viewed?: boolean; playback_step?: number;
  complete?: boolean; game_result?: Record<string, unknown>;
  source?: "SDK_REPORTED" | "USER_CONFIRMED";
};
type SaveBody = { playback_step?: number; base_revision: number; event_id: string; scene_id?: string | null; game_state?: Record<string, unknown> | null };
type Entry = { patch: ActivityPatch; body?: SaveBody };

/** Failed requests retain their exact body/event ID, including lost responses. */
export class ActivitySaveQueue {
  private entries: Entry[] = [];
  private running: Promise<InteractiveSession | null> | null = null;
  private epoch = 0;
  constructor(private readonly options: {
    session: () => InteractiveSession | null;
    saved: (session: InteractiveSession) => void;
    status: (status: "saving" | "saved" | "unsaved", error?: string) => void;
  }) {}
  get dirty() { return this.entries.length > 0; }
  reset() { this.epoch++; this.entries = []; this.running = null; }
  enqueue(patch: ActivityPatch) {
    this.entries.push({ patch: structuredClone(patch) });
    return this.flush();
  }
  flush(): Promise<InteractiveSession | null> {
    if (this.running) return this.running;
    if (!this.entries.length) return Promise.resolve(this.options.session());
    const epoch = this.epoch;
    this.options.status("saving");
    const task = (async () => {
      let saved = this.options.session();
      while (this.entries.length && epoch === this.epoch) {
        const entry = this.entries[0];
        const session = this.options.session();
        if (!session) throw new Error("活动已切换");
        entry.body ??= {
          base_revision: session.base_revision, event_id: crypto.randomUUID(),
          scene_id: entry.patch.scene_id ?? session.current_scene_id,
          ...(entry.patch.playback_step === undefined ? {} : {playback_step: entry.patch.playback_step}),
          ...(entry.patch.game_state === undefined ? {} : { game_state: entry.patch.game_state }),
        };
        saved = entry.patch.viewed
          ? await viewedInteractive(session.id, {base_revision: entry.body.base_revision, event_id: entry.body.event_id})
          : entry.patch.complete
          ? await completeInteractive(session.id, { ...entry.body, game_result: entry.patch.game_result, source: entry.patch.source })
          : await saveInteractive(session.id, entry.body);
        if (epoch !== this.epoch) return null;
        const current = this.options.session();
        if (saved.id !== session.id || saved.revision_id !== session.revision_id) throw new Error("活动回执不匹配，请重新读取");
        if (!current || saved.base_revision >= current.base_revision) this.options.saved(saved);
        else saved = current;
        this.entries.shift();
      }
      if (epoch === this.epoch) this.options.status("saved");
      return saved;
    })().catch((error: unknown) => {
      if (epoch === this.epoch) this.options.status("unsaved", error instanceof Error ? error.message : "保存失败");
      throw error;
    }).finally(() => { if (epoch === this.epoch) this.running = null; });
    this.running = task;
    return task;
  }
}
