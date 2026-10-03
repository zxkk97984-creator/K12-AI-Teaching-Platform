import { cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";
import { afterEach,beforeEach,describe,expect,it,vi } from "vitest";
import { QuizGenerationCard } from "./QuizGenerationCard";
import { generateConversationQuiz,getConversationQuizOptions,type StudentGenerationJob } from "../quiz/api";
import { ConversationContext } from "./ConversationProvider";
import { ConversationController } from "./controller";

vi.mock("../quiz/api", () => ({ generateConversationQuiz:vi.fn(),getConversationQuizOptions:vi.fn() }));
const queued:StudentGenerationJob = { id:"quiz-job",status:"QUEUED",error_code:null,quiz_session_id:null,request_summary:{count:20,generated_count:0} };
const props = { conversationId:"conversation-test",messageId:"message-test",suggestedTopic:"条件与循环",onJob:vi.fn() };
const show = () => render(<ConversationContext.Provider value={new ConversationController()}><QuizGenerationCard {...props} /></ConversationContext.Provider>);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getConversationQuizOptions).mockResolvedValue({stage:"JUNIOR",max_question_count:20,allowed_difficulties:["EASY","MEDIUM"],allowed_question_types:["SINGLE_CHOICE"]});
  vi.mocked(generateConversationQuiz).mockResolvedValue({job:queued,quiz:null});
});
afterEach(cleanup);
describe("inline count selection", () => {
  it("keeps quantity controls in the dialogue", async () => {
    show(); fireEvent.click(screen.getByRole("button",{name:"生成小练习"}));
    await screen.findByRole("button",{name:"开始生成"});
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button",{name:"20 题"}));
    fireEvent.click(screen.getByRole("button",{name:"开始生成"}));
    await waitFor(() => expect(props.onJob).toHaveBeenCalledOnce());
    expect(generateConversationQuiz).toHaveBeenCalledWith(expect.objectContaining({questionCount:20}));
  });
  it("rejects fractions and values outside the supported total", async () => {
    show(); fireEvent.click(screen.getByRole("button",{name:"生成小练习"}));
    await screen.findByRole("button",{name:"开始生成"});
    for (const value of ["0","21","1.5"]) {
      fireEvent.change(screen.getByLabelText("自定义题数"),{target:{value}});
      expect((screen.getByRole("button",{name:"开始生成"}) as HTMLButtonElement).disabled).toBe(true);
    }
    expect(generateConversationQuiz).not.toHaveBeenCalled();
  });
  it("retries exactly the accepted settings and idempotency key", async () => {
    vi.mocked(generateConversationQuiz).mockRejectedValueOnce(new Error("临时不可用"));
    show(); fireEvent.click(screen.getByRole("button",{name:"生成小练习"}));
    await screen.findByRole("button",{name:"开始生成"});
    fireEvent.click(screen.getByRole("button",{name:"10 题"}));
    fireEvent.click(screen.getByRole("button",{name:"开始生成"}));
    await screen.findByText("临时不可用");
    const first=vi.mocked(generateConversationQuiz).mock.calls[0][0];
    fireEvent.click(screen.getByRole("button",{name:"开始生成"}));
    await waitFor(() => expect(props.onJob).toHaveBeenCalledOnce());
    expect(vi.mocked(generateConversationQuiz).mock.calls[1][0]).toEqual(first);
  });
});
