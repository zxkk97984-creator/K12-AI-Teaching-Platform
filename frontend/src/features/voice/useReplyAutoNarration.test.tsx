import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AccountProvider } from "../identity/AccountContext";
import { ConversationContext } from "../conversation/ConversationProvider";
import { ConversationController } from "../conversation/controller";
import { useReplyAutoNarration } from "./useReplyAutoNarration";
import { useNarration } from "../interactive/useNarration";
import type { MeResponse } from "../identity/types";
import type { RunDTO } from "../conversation/types";
const account: MeResponse = {user:{id:"a",username:"a",role:"student",is_active:true},profile:null,preferences:{preferred_style:"AUTO",teacher_style:"AUTO",companion_pet_id:"shuangling",interests:[],proactive_guidance_enabled:true,voice_preference:"INPUT_AND_OUTPUT",auto_read_replies:true,profile_revision:0}};
afterEach(() => {cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});
function setup(me = account, alreadyComplete = false) {
  vi.stubGlobal("SpeechSynthesisUtterance", class {constructor(public text: string) {}});
  const synthesis = {getVoices:()=>[{lang:"zh-CN"}],cancel:vi.fn(),speak:vi.fn((speech:{onstart:()=>void})=>speech.onstart())};
  vi.stubGlobal("speechSynthesis",synthesis);
  const controller = new ConversationController();
  let run: RunDTO | null = alreadyComplete ? {id:"old-run",session_id:"s",status:"SUCCEEDED",card:{message_markdown:"历史回复",source_refs:[],evidence_refs:[],warnings:[],fixture:true}} as unknown as RunDTO : null;
  let fresh = true;
  const claim = vi.spyOn(controller,"claimReplyNarration").mockImplementation(value => {
    if(value.status !== "SUCCEEDED" || !value.card || !fresh) return false;
    fresh = false; return true;
  });
  vi.spyOn(controller,"getSnapshot").mockImplementation(() => ({reference:null,quizRequest:null,quizJobs:[],sessions:[],chapters:[],detail:{id:"s",messages:[]} as never,draft:"",run,loading:false,selecting:false,sending:false,transport:null,error:null}));
  // Cache the snapshot exactly as useSyncExternalStore requires.
  const getter = controller.getSnapshot;
  let snapshot = getter();
  vi.spyOn(controller,"getSnapshot").mockImplementation(()=>snapshot);
  const wrapper = ({children}:{children:React.ReactNode})=><AccountProvider me={me}><ConversationContext.Provider value={controller}>{children}</ConversationContext.Provider></AccountProvider>;
  const hook = renderHook(()=>useReplyAutoNarration(),{wrapper});
  const update = (status: RunDTO["status"]) => {
    run = {id:"run",session_id:"s",status,operation:"TEACH_TURN",attempt:1,fixture:true,error_category:null,stale_reason:null,created_at:"2026-10-02",started_at:null,completed_at:null,idempotent_replay:false,result_message_id:"m",card:{message_markdown:"**解释**正文",source_refs:[],evidence_refs:[],warnings:[],fixture:true}} as RunDTO;
    snapshot={...snapshot,run}; hook.rerender();
  };
  return {hook,update,synthesis,claim,wrapper};
}
it("reads new completion once while drafts remain silent", async()=> {
  const test=setup();
  act(()=>test.update("RUNNING"));expect(test.synthesis.speak).not.toHaveBeenCalled();
  await act(async()=>test.update("SUCCEEDED"));expect(test.synthesis.speak).toHaveBeenCalledOnce();
  await act(async()=>test.update("SUCCEEDED"));expect(test.synthesis.speak).toHaveBeenCalledOnce();
});
it.each([false,true])("consumes completion without speech when auto=%s and output is disabled",async auto=>{
  const test=setup({...account,preferences:{...account.preferences!,auto_read_replies:auto,voice_preference:"INPUT_ONLY"}});
  await act(async()=>test.update("SUCCEEDED"));
  expect(test.synthesis.speak).not.toHaveBeenCalled();expect(test.claim).toHaveBeenCalled();
});
it("yields once to a reader and exposes a manual retry note",async()=>{
  const test=setup();
  const reader=renderHook(()=>useNarration(()=>""),{wrapper:test.wrapper});
  await act(async()=>reader.result.current.play({id:"chapter",scene_id:"c",text:"课文",audio:null,trigger:"MANUAL"}));
  await act(async()=>test.update("SUCCEEDED"));
  expect(test.synthesis.speak).toHaveBeenCalledOnce();expect(test.hook.result.current.notice).toContain("未自动朗读");
  act(()=>reader.result.current.stop()); await act(async()=>test.update("SUCCEEDED"));
  expect(test.synthesis.speak).toHaveBeenCalledOnce();
});

it("opening a surface after the reply has already completed does not play it", () => {
  const test = setup(account, true);
  expect(test.claim).toHaveBeenCalled();
  expect(test.synthesis.speak).not.toHaveBeenCalled();
});
it("default-off automatic narration consumes a new completion without speech", async () => {
  const test = setup({...account, preferences:{...account.preferences!,auto_read_replies:false}});
  await act(async () => test.update("SUCCEEDED"));
  expect(test.synthesis.speak).not.toHaveBeenCalled();
});
