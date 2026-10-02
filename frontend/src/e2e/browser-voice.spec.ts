import { expect, test, type Page } from "@playwright/test";
import { fixture, session } from "./ui-reuse-fixtures";
import { readFileSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";

async function voiceFixture(page: Page) {
  const state = await fixture(page);
  state.account.preferences.voice_preference = "INPUT_AND_OUTPUT";
  Object.assign(state.account.preferences, { auto_read_replies: true });
  await page.route("**/api/v1/quiz-options/conversation", route => route.fulfill({json:{stage:"JUNIOR",max_question_count:3,allowed_difficulties:["EASY"],allowed_question_types:["CHOICE"]}}));
  await page.route("**/api/v1/quiz-generation-jobs**", route => route.fulfill({json:{items:[]}}));
  await page.route("**/api/v1/content/page-context", async route => {
    const value = route.request().postDataJSON();
    await route.fulfill({json:{source_id:"chapter-ui",revision:1,block_id:value.block_id,section_key:null,selected_text:value.selected_text,selected_text_chars:value.selected_text.length}});
  });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (["error", "warning"].includes(message.type())) errors.push(message.text()); });
  await page.addInitScript(() => {
    const control = window as typeof window & { voiceTest: {
      captures: Array<{ onresult?: (event: unknown) => void; onerror?: (event: unknown) => void; onend?: () => void; stopped: boolean; aborted: boolean }>;
      spoken: Array<{ text: string; rate: number; lang: string; onstart?: () => void; onend?: () => void }>;
      cancelled: number;
    } };
    const state: typeof control.voiceTest = { captures: [], spoken: [], cancelled: 0 };
    control.voiceTest = state;
    class Recognition {
      lang = ""; continuous = false; interimResults = false; stopped = false; aborted = false;
      onresult?: (event: unknown) => void; onerror?: (event: unknown) => void; onend?: () => void;
      constructor() { state.captures.push(this); }
      start() {} stop() { this.stopped = true; } abort() { this.aborted = true; }
    }
    Object.defineProperty(window, "SpeechRecognition", { configurable: true, value: Recognition });
    Object.defineProperty(window, "SpeechSynthesisUtterance", { configurable: true, value: class { text: string; rate = 1; lang = ""; constructor(text: string) { this.text = text; } } });
    Object.defineProperty(window, "speechSynthesis", { configurable: true, value: {
      getVoices: () => [{ lang: "zh-CN", name: "受控普通话", voiceURI: "mock-zh", default: true }],
      addEventListener() {}, removeEventListener() {}, paused: false,
      cancel() { state.cancelled++; }, resume() {},
      speak(speech: typeof state.spoken[number]) { state.spoken.push(speech); speech.onstart?.(); },
    } });
  });
  return { state, errors };
}
async function result(page: Page, text: string) {
  await page.evaluate(text => {
    const control = window as unknown as { voiceTest: { captures: Array<{onresult: (event: unknown) => void}> } };
    control.voiceTest.captures.at(-1)!.onresult({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: text } }] });
  }, text);
}
async function capture(page: Page, name: string) {
  await mkdir("test-results/browser-voice", {recursive: true});
  await page.screenshot({path: `test-results/browser-voice/${name}.png`, animations: "disabled"});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.title()).not.toBe("");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
}

for (const width of [1366, 390]) test(`full chat and companion keep editable speech drafts and cancel on close at ${width}px`, async ({page}) => {
  const { state, errors } = await voiceFixture(page);
  await page.setViewportSize({width, height: 900});
  await page.goto(`/conversations?session=${session.id}`);
  const full = page.locator(".conversation-content--full");
  const draft = full.locator("textarea");
  await draft.fill("原有草稿");
  await full.getByRole("button", {name: "开始语音输入"}).click();
  await expect(full.getByText("正在听，请说话…")).toBeVisible();
  await draft.fill("手动修改");
  await result(page, "请讲解分类");
  await expect(draft).toHaveValue("手动修改 请讲解分类");
  expect(state.turns).toBe(0);
  await full.getByRole("button", {name: "停止语音输入"}).click();
  await page.evaluate(() => (window as unknown as {voiceTest:{captures:Array<{onend:()=>void}>}}).voiceTest.captures.at(-1)!.onend());
  await expect(full.getByRole("button", {name:"开始语音输入"})).toBeEnabled();
  await capture(page, `chat-${width}`);
  await page.getByRole("button", {name:"打开霜铃学习助手"}).click();
  const panel = page.locator("#companion-panel");
  await panel.getByRole("button", {name:"开始语音输入"}).click();
  await result(page,"桌宠问题");
  await expect(panel.locator("textarea")).toHaveValue("手动修改 请讲解分类 桌宠问题");
  await capture(page, `companion-${width}`);
  await panel.getByRole("button",{name:"收起对话"}).click();
  expect(await page.evaluate(() => (window as unknown as {voiceTest:{captures:Array<{aborted:boolean}>}}).voiceTest.captures.at(-1)!.aborted)).toBe(true);
  await expect(draft).toHaveValue("手动修改 请讲解分类 桌宠问题");
  expect(state.turns).toBe(0);
  expect(errors).toEqual([]);
});

test("new completed reply reads once, history is silent, manual control pauses and resumes", async ({page}) => {
  const { state, errors } = await voiceFixture(page);
  const markdown = "**老师解释**：看[课程](https://test.invalid/course)。\n```json\n{\"internal_id\":\"secret\"}\n```";
  const card = {message_markdown: markdown, source_refs:[], evidence_refs:[], warnings:[], fixture:true};
  const completed = {id:"new-voice-run",session_id:session.id,operation:"TEACH_TURN",status:"SUCCEEDED",card,result_message_id:"new-voice-message",idempotent_replay:false,completed_at:session.created_at,created_at:session.created_at};
  state.messages = [{id:"old-reply",role:"ASSISTANT",content_markdown:"旧回复不自动播放。",card:{...card,message_markdown:"旧回复不自动播放。"},created_at:session.created_at}];
  await page.route(`**/api/v1/conversations/${session.id}/messages`, async route => { state.messages.push({id:"new-voice-message",role:"ASSISTANT",content_markdown:markdown,card,created_at:session.created_at}); await route.fulfill({json:{run:completed}}); });
  await page.goto(`/conversations?session=${session.id}`);
  const full = page.locator(".conversation-content--full");
  await expect(full.getByTestId("assistant-card")).toHaveCount(1);
  expect(await page.evaluate(() => (window as unknown as {voiceTest:{spoken:unknown[]}}).voiceTest.spoken.length)).toBe(0);
  await full.locator("textarea").fill("新问题"); await full.getByTestId("send-turn").click();
  await expect.poll(() => page.evaluate(() => (window as unknown as {voiceTest:{spoken:unknown[]}}).voiceTest.spoken.length)).toBe(1);
  expect(await page.evaluate(() => (window as unknown as {voiceTest:{spoken:Array<{text:string}>}}).voiceTest.spoken[0].text)).toBe("老师解释：看课程。");
  const latest = full.locator(".conv-message-assistant").last();
  await latest.getByRole("button",{name:"朗读回复"}).click();
  await expect(latest.getByRole("button",{name:"朗读回复"})).toHaveText("暂停朗读");
  await latest.getByRole("button",{name:"朗读回复"}).click();
  await expect(latest.getByRole("button",{name:"朗读回复"})).toHaveText("继续朗读");
  await latest.getByRole("button",{name:"朗读回复"}).click();
  await latest.getByRole("button",{name:"停止朗读"}).click();
  await capture(page,"reply-controls");
  await page.reload(); await expect(full.getByTestId("assistant-card")).toHaveCount(2);
  expect(await page.evaluate(() => (window as unknown as {voiceTest:{spoken:unknown[]}}).voiceTest.spoken.length)).toBe(0);
  expect(errors).toEqual([]);
});

test("settings share speed with chapter and selected narration; microphone takes ownership", async ({page}) => {
  const { errors } = await voiceFixture(page);
  await page.goto("/settings");
  await page.getByLabel("朗读语速",{exact:true}).selectOption("1.5");
  await page.goto("/chapters/chapter-ui");
  await page.getByRole("button",{name:"朗读本章",exact:true}).click();
  await expect(page.getByRole("button",{name:"暂停朗读",exact:true})).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as {voiceTest:{spoken:Array<{rate:number}>}}).voiceTest.spoken[0].rate)).toBe(1.5);
  await page.getByRole("button",{name:"暂停朗读",exact:true}).click();
  await page.getByRole("button",{name:"继续朗读",exact:true}).click();
  await page.evaluate(() => {
    const text = document.querySelector('[data-block-id="b2"]')!;
    const range = document.createRange(); range.selectNodeContents(text);
    const selection=window.getSelection()!;selection.removeAllRanges();selection.addRange(range);
    text.dispatchEvent(new MouseEvent("mouseup", {bubbles:true}));
  });
  await page.getByRole("button",{name:"朗读这段",exact:true}).click();
  await page.getByRole("button",{name:"打开霜铃学习助手"}).click();
  await page.locator("#companion-panel").getByRole("button",{name:"开始语音输入"}).click();
  await expect(page.getByRole("button",{name:"播放本章",exact:true})).toBeVisible();
  await capture(page,"reader-microphone");
  expect(errors).toEqual([]);
});

test("compact composer keeps idle speech quiet and shows recording and permission errors", async ({ page }) => {
  const { errors } = await voiceFixture(page);
  await page.goto(`/conversations?session=${session.id}`);
  await page.getByRole("button", { name: "打开霜铃学习助手" }).click();
  const panel = page.locator("#companion-panel");
  const feedback = panel.locator(".conv-voice-feedback");
  await expect(feedback).toBeEmpty();
  expect((await panel.locator(".conv-composer").boundingBox())!.height).toBeLessThanOrEqual(76);
  await panel.getByRole("button", { name: "开始语音输入", exact: true }).click();
  await expect(feedback).toContainText("正在听");
  await page.evaluate(() => (window as unknown as {voiceTest:{captures:Array<{onerror:(event:unknown)=>void}>}}).voiceTest.captures.at(-1)!.onerror({error:"not-allowed"}));
  await expect(panel.getByRole("alert")).toContainText("麦克风权限被拒绝");
  await panel.getByLabel("想对老师说什么").fill("继续使用文字提问");
  await expect(panel.getByTestId("send-turn")).toBeEnabled();
  expect(errors).toEqual([]);
});

test("permission rejection and unsupported browser keep keyboard input usable", async ({page}) => {
  const {errors}=await voiceFixture(page); await page.goto(`/conversations?session=${session.id}`);
  const full=page.locator(".conversation-content--full");
  await full.getByRole("button",{name:"开始语音输入"}).click();
  await page.evaluate(() => (window as unknown as {voiceTest:{captures:Array<{onerror:(event:unknown)=>void}>}}).voiceTest.captures.at(-1)!.onerror({error:"not-allowed"}));
  await expect(full.getByRole("alert")).toContainText("麦克风权限被拒绝");
  await full.locator("textarea").fill("仍可打字"); await expect(full.getByTestId("send-turn")).toBeEnabled();
  await capture(page,"permission-denied");
  await page.addInitScript(() => {Object.defineProperty(window,"SpeechRecognition",{value:undefined,configurable:true});Object.defineProperty(window,"webkitSpeechRecognition",{value:undefined,configurable:true});});
  await page.reload(); await expect(full.getByText("当前浏览器不支持语音输入，可直接打字。")).toBeVisible();
  await full.locator("textarea").fill("纯文字问题"); await expect(full.getByTestId("send-turn")).toBeEnabled();
  expect(errors).toEqual([]);
});

test("records actual Chrome speech capabilities without claiming audible speech or recognized input", async ({page}) => {
  const state = await fixture(page); state.account.preferences.voice_preference = "INPUT_AND_OUTPUT";
  await page.route("**/api/v1/quiz-options/conversation", route => route.fulfill({json:{stage:"JUNIOR",max_question_count:3,allowed_difficulties:["EASY"],allowed_question_types:["CHOICE"]}}));
  await page.route("**/api/v1/quiz-generation-jobs**", route => route.fulfill({json:{items:[]}}));
  await page.goto("/settings");
  await page.waitForTimeout(1600);
  const evidence = await page.evaluate(async () => ({
    userAgent:navigator.userAgent,
    speechRecognition:Boolean((window as unknown as {SpeechRecognition?:unknown;webkitSpeechRecognition?:unknown}).SpeechRecognition || (window as unknown as {webkitSpeechRecognition?:unknown}).webkitSpeechRecognition),
    synthesis:Boolean(window.speechSynthesis),
    voices:window.speechSynthesis?.getVoices().map(v=>({name:v.name,lang:v.lang,localService:v.localService})),
    mediaDevices:Boolean(navigator.mediaDevices),
    microphonePermission: await navigator.permissions.query({name:"microphone" as PermissionName}).then(p=>p.state).catch(()=>"unavailable"),
    audioInputCount: await navigator.mediaDevices.enumerateDevices().then(devices=>devices.filter(d=>d.kind==="audioinput").length).catch(()=>null),
    audibleSpeechVerified:false,actualRecognitionVerified:false,
  }));
  await mkdir("test-results/browser-voice",{recursive:true});
  await capture(page,"actual-voice-settings");
  await page.goto(`/conversations?session=${session.id}`);
  const full=page.locator(".conversation-content--full");
  const microphone=full.getByRole("button",{name:"开始语音输入"});
  if(await microphone.isEnabled()) {
    await microphone.click();
    await page.waitForTimeout(3000);
  }
  const actualInputNotice=await full.locator(".conv-voice-feedback").textContent();
  await writeFile("test-results/browser-voice/actual-capabilities.json",JSON.stringify({...evidence,actualInputNotice},null,2));
  await capture(page,"actual-microphone-attempt");
});

for (const width of [1366,390]) test(`interactive packaged audio stays preferred and microphone cancels it at ${width}px`, async ({page}) => {
  const {errors}=await voiceFixture(page);
  const bridge=readFileSync(new URL("../../../backend/app/modules/interactive/bridge.js",import.meta.url),"utf8");
  const manifest={schema_version:"k12-interactive-v1",content_key:"voice-test",title:"语音集成课件",purpose:"GAME",stage:"JUNIOR",subject:"数学",entry:"index.html",cover:null,summary:"受控音频测试",knowledge_points:[],capabilities:["SCENES","CHECKPOINTS","COMPLETION"],scenes:[{id:"main",title:"开始",summary:"观察"}],prompts:[{id:"audio-prompt",scene_id:"main",text:"包内音频讲解。",trigger:"MANUAL",audio:"audio/intro.wav"}]};
  const activity={id:"interactive-session-ui",resource_id:"interactive-ui",revision_id:"interactive-version-ui",stage:"JUNIOR",status:"ACTIVE",base_revision:0,current_scene_id:"main",game_state:{},host_state:{},game_result:null,completion_source:null,created_at:session.created_at,updated_at:session.created_at,completed_at:null};
  const html=`<!doctype html><html><head><script>${bridge}</script></head><body><h1>语音集成课件</h1><script>K12.ready();</script></body></html>`;
  await page.route("**/api/v1/interactive/sessions",route=>route.fulfill({json:route.request().method()==="POST"?activity:{items:[]}}));
  await page.route("**/api/v1/interactive/sessions/interactive-session-ui/checkpoint",route=>route.fulfill({json:{...activity,base_revision:route.request().postDataJSON().base_revision+1}}));
  await page.route("**/api/v1/interactive/sessions/interactive-session-ui",route=>route.fulfill({json:{session:activity,resource:{id:"interactive-ui",title:manifest.title,purpose:"GAME",subject:"数学"},manifest}}));
  await page.route("**/api/v1/interactive/sessions/interactive-session-ui/document",route=>route.fulfill({json:{session_id:activity.id,revision_id:activity.revision_id,document_html:html,manifest}}));
  await page.addInitScript(()=>{
    const control=window as unknown as {voiceAudio:Array<{src:string;playbackRate:number;paused:boolean;onplaying?:()=>void;onpause?:()=>void;onended?:()=>void}>};control.voiceAudio=[];
    class Audio {
      playbackRate=1;paused=true;ended=false;onplaying?:()=>void;onpause?:()=>void;onended?:()=>void;
      constructor(public src:string){control.voiceAudio.push(this);}
      async play(){this.paused=false;this.onplaying?.();}
      pause(){this.paused=true;this.onpause?.();}
    }
    Object.defineProperty(window,"Audio",{value:Audio,configurable:true});
  });
  await page.setViewportSize({width,height:900});
  await page.goto("/interactive/interactive-ui");
  await page.getByRole("button",{name:"开始学习",exact:true}).click();
  await page.getByRole("button",{name:"播放讲解",exact:true}).click();
  await expect(page.getByRole("button",{name:"暂停讲解",exact:true})).toBeVisible();
  expect(await page.evaluate(()=>(window as unknown as {voiceTest:{spoken:unknown[]}}).voiceTest.spoken.length)).toBe(0);
  await page.getByLabel("声音设置",{exact:true}).click();
  await expect(page.getByLabel("朗读声音",{exact:true})).toBeDisabled();
  await page.getByLabel("朗读语速",{exact:true}).selectOption("1.5");
  await page.getByLabel("声音设置",{exact:true}).click();
  await page.getByRole("button",{name:"暂停讲解",exact:true}).click();
  await page.getByRole("button",{name:"继续讲解",exact:true}).click();
  await capture(page,`interactive-audio-${width}`);
  await page.getByRole("button",{name:"打开霜铃学习助手"}).click();
  await page.locator("#companion-panel").getByRole("button",{name:"开始语音输入"}).click();
  expect(await page.evaluate(()=>(window as unknown as {voiceAudio:Array<{paused:boolean}>}).voiceAudio.every(audio=>audio.paused))).toBe(true);
  await page.locator("#companion-panel textarea").fill("");
  await result(page,"我想问这个实验");
  await expect(page.locator("#companion-panel textarea")).toHaveValue("我想问这个实验");
  await expect(page.locator("#companion-panel").getByText("正在听，请说话…",{exact:true})).toBeVisible();
  await capture(page,`interactive-microphone-${width}`);
  await page.locator("#companion-panel").getByRole("button",{name:"收起对话"}).click();
  expect(errors).toEqual([]);
});
