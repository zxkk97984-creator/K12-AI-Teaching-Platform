import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { QuizGenerationProgress } from "./QuizGenerationProgress";
import type { StudentGenerationJob } from "../quiz/api";

afterEach(cleanup);
it("shows the saved question count without inventing completed progress",()=>{
  const job:StudentGenerationJob = {id:"progress-test",status:"RUNNING",error_code:null,quiz_session_id:null,request_summary:{count:20,generated_count:0}};
  const {rerender,container} = render(<QuizGenerationProgress job={job} />);
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("0");
  expect(container.querySelector<HTMLElement>(".quiz-generation-fill")?.style.width).toBe("0%");
  rerender(<QuizGenerationProgress job={{...job,request_summary:{count:20,generated_count:5}}} />);
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("5");
  expect(container.querySelector<HTMLElement>(".quiz-generation-fill")?.style.width).toBe("25%");
  expect(screen.getByRole("status").textContent).toBe("已生成 5／20 题");
});
it("keeps an unknown total indeterminate",()=>{
  render(<QuizGenerationProgress job={{id:"old-progress",status:"QUEUED",error_code:null,quiz_session_id:null}} />);
  expect(screen.getByRole("progressbar").hasAttribute("aria-valuenow")).toBe(false);
  expect(screen.getByText("马上开始，请稍等")).toBeTruthy();
});
