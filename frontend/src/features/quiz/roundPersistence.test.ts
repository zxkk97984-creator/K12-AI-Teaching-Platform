import {beforeEach,expect,it,vi} from "vitest";
import {waitFor} from "@testing-library/react";
import {QuizRoundPersistence} from "./roundPersistence";
import {saveQuizPosition} from "./api";
import {quizChapterRevision} from "./types";

vi.mock("./api",()=>({saveQuizPosition:vi.fn()}));
beforeEach(()=>vi.resetAllMocks());
it("uses a saved group's chapter revision when the current page has changed",()=>{
  expect(quizChapterRevision({chapter_id:"old-chapter",curriculum_revision:"old-revision:2"})).toBe(2);
  expect(quizChapterRevision({chapter_id:null,curriculum_revision:"conversation:2"})).toBeNull();
  expect(quizChapterRevision({chapter_id:"old-chapter",curriculum_revision:"legacy-release"})).toBeNull();
});
it("keeps the final position when a student flips faster than the first save",async()=>{
  let resolve!: (value:{position:number})=>void;
  vi.mocked(saveQuizPosition).mockReturnValueOnce(new Promise(done=>{resolve=done;})).mockResolvedValueOnce({position:2});
  const state=new QuizRoundPersistence();
  const first=state.position("quiz",1),second=state.position("quiz",2);
  await waitFor(()=>expect(saveQuizPosition).toHaveBeenCalledTimes(1));
  resolve({position:1}); await Promise.all([first,second]);
  expect(vi.mocked(saveQuizPosition).mock.calls).toEqual([["quiz",1],["quiz",2]]);
});
it("lets a later position save continue after a failed write",async()=>{
  vi.mocked(saveQuizPosition).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({position:2});
  const state=new QuizRoundPersistence();
  const first=state.position("quiz",1).catch(()=>undefined),second=state.position("quiz",2);
  await Promise.all([first,second]);
  expect(saveQuizPosition).toHaveBeenLastCalledWith("quiz",2);
});
