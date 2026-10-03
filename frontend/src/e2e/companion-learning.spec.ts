import { expect,test,type Locator,type Page } from "@playwright/test";
import { fixture,session } from "./ui-reuse-fixtures";

async function expectMenuTextReadable(item: Locator) {
  await expect.poll(() => item.evaluate(element => {
    const luminance = (color: string) => {
      const rgb = color.match(/[\d.]+/g)!.slice(0,3).map(Number).map(value => {
        const channel = value / 255;
        return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
      });
      return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
    };
    const background = luminance(getComputedStyle(element).backgroundColor);
    return Math.min(...[element.querySelector('span:last-child')!,element.querySelector('small')!].map(text => {
      const foreground = luminance(getComputedStyle(text).color);
      return (Math.max(foreground,background) + .05) / (Math.min(foreground,background) + .05);
    }));
  })).toBeGreaterThanOrEqual(4.5);
}

for (const stage of ["PRIMARY_LOWER","PRIMARY_UPPER","JUNIOR","SENIOR"]) {
  test(`${stage} full-body companion choice survives shrinking, navigation and refresh`,async({page})=>{
    test.setTimeout(90_000);
    const state=await fixture(page,{stage,rich:true,interactive:true,interactivePurpose:"GAME",codeRunnerAvailable:true});
    const errors:string[]=[];
    page.on("pageerror",error=>errors.push(error.message));
    await page.setViewportSize({width:1440,height:900});
    await page.goto("/workbench");
    await expect(page.getByTestId("workbench-shell")).toBeVisible();
    const dock=page.getByTestId("companion-dock");
    const toggle=dock.locator(".companion-toggle");
    const sprite=dock.locator(".companion-sprite");
    const panel=page.locator("#companion-panel");
    await expect(dock).toHaveAttribute("data-minimized","true");
    await toggle.click();
    await panel.getByRole("textbox").fill("我想再了解一下这部分内容");
    await panel.getByRole("button",{name:"更多选项",exact:true}).click();
    const display=panel.getByLabel("桌宠显示方式");
    await display.selectOption("full");
    await expect(dock).toHaveAttribute("data-minimized","false");
    await expect(dock).toHaveAttribute("data-compact","false");
    await expect(sprite).toHaveCSS("width","104px");
    await expect(sprite).toHaveCSS("background-image",/spritesheet-extended\.webp/);
    await expect(panel.getByRole("textbox")).toHaveValue("我想再了解一下这部分内容");
    await panel.getByRole("button",{name:"收起对话",exact:true}).click();
    await expect(sprite).toBeVisible();
    await page.getByRole("navigation",{name:"学生导航"}).locator('a[href="/resources"]').click();
    await expect(page).toHaveURL(/\/resources$/);
    await expect(dock).toHaveAttribute("data-minimized","false");
    await toggle.click();
    await expect(panel.getByRole("textbox")).toHaveValue("我想再了解一下这部分内容");
    await panel.getByRole("button",{name:"收起对话",exact:true}).click();
    await page.reload();
    await expect(sprite).toBeVisible();
    await toggle.click();
    await panel.getByRole("textbox").fill("我想再了解一下这部分内容");
    // Shrinking is an appearance change; it must leave the current chat intact.
    await dock.getByRole("button",{name:"缩小桌宠",exact:true}).click();
    await expect(dock).toHaveAttribute("data-minimized","true");
    await expect(panel).toBeVisible();
    await expect(panel.getByRole("textbox")).toHaveValue("我想再了解一下这部分内容");
    await panel.getByRole("button",{name:"更多选项",exact:true}).click();
    await display.selectOption("full");
    await expect(sprite).toBeVisible();
    await panel.getByRole("button",{name:"收起对话",exact:true}).click();
    await page.getByRole("navigation",{name:"学生导航"}).locator('a[href="/workbench"]').click();
    await expect(page.getByTestId("workbench-shell")).toBeVisible();
    for (const width of [320,390,768,1440]) {
      await page.setViewportSize({width,height:900});
      await expect(sprite).toBeInViewport();
      await expect.poll(async()=>{
        const bounds=(await dock.boundingBox())!;
        return bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= width && bounds.y + bounds.height <= 900 - (width <= 820 ? 76 : 0);
      }).toBe(true);
      await page.screenshot({path:`test-results/companion-full-${stage}-${width}.png`});
      await toggle.click();
      await expect(panel).toBeInViewport();
      await expect(panel.getByRole("textbox")).toHaveValue("我想再了解一下这部分内容");
      await panel.getByRole("button",{name:"收起对话",exact:true}).click();
      await expect(dock).toHaveAttribute("data-minimized","false");
    }
    const beforeMove=(await dock.boundingBox())!;
    await toggle.press("ArrowLeft");
    await expect.poll(async()=>(await dock.boundingBox())!.x).toBe(Math.max(12,beforeMove.x - 24));
    await expect(panel).toHaveCount(0);
    for (const route of ["/chapters/chapter-ui","/practice","/history","/growth","/settings","/onboarding","/more","/conversations","/books/python3","/picturebooks",...(stage === "PRIMARY_LOWER" ? ["/picturebooks/crow"] : []),"/animations","/interactive/interactive-ui","/code?task=double&revision=1"]) {
      await page.goto(route);
      await expect(page.locator("#page-content .route-load-state")).toHaveCount(0);
      await expect(dock).toHaveAttribute("data-minimized","false");
      await expect(sprite).toBeInViewport();
    }
    await page.getByRole("button",{name:"专注模式",exact:true}).click();
    await expect(page.getByTestId("codelab-workspace")).toHaveAttribute("data-focus-mode","true");
    await expect(sprite).toBeInViewport();
    await toggle.click();
    await expect(panel.getByRole("textbox")).toBeVisible();
    await page.screenshot({path:`test-results/companion-full-focus-${stage}-1440.png`});
    await panel.getByRole("button",{name:"收起对话",exact:true}).click();
    await page.getByRole("button",{name:"退出专注 Esc",exact:true}).click();
    await toggle.click();
    await panel.getByRole("button",{name:"更多选项",exact:true}).click();
    await display.selectOption("compact");
    await panel.getByRole("button",{name:"收起对话",exact:true}).click();
    for (const route of ["/study","/resources","/settings","/books/python3"]) {
      await page.goto(route);
      await expect(page.locator("#page-content .route-load-state")).toHaveCount(0);
      await expect(dock).toHaveAttribute("data-minimized","true");
      await expect(toggle).toBeInViewport();
    }
    expect(state.starts).toBe(0);
    expect(errors).toEqual([]);
  });
}

test("full-body mode reuses every selected companion and preserves a dragged position",async({page})=>{
  const state=await fixture(page,{stage:"JUNIOR"});
  await page.setViewportSize({width:1440,height:900});
  await page.goto("/workbench");
  const dock=page.getByTestId("companion-dock");
  const toggle=dock.locator(".companion-toggle");
  const panel=page.locator("#companion-panel");
  const sprite=dock.locator(".companion-sprite");
  await toggle.click();
  await panel.getByRole("button",{name:"更多选项",exact:true}).click();
  await panel.getByLabel("桌宠显示方式").selectOption("full");
  for (const [id,name,image] of [["anya","阿尼亚","/pets/anya/"],["doraemon","哆啦A梦","/pets/doraemon/"],["kun-like","Kun Like","/pets/kun-like/"],["lulu-capybara","噜噜","/pets/lulu-capybara/"],["shinchan","小新","/pets/shinchan/"],["shuangling","霜铃","/spritesheet-extended.webp"]]) {
    if (await panel.getByRole("button",{name:"更多选项",exact:true}).getAttribute("aria-expanded") !== "true") {
      await panel.getByRole("button",{name:"更多选项",exact:true}).click();
    }
    await panel.getByRole("tab",{name:"学习伙伴",exact:true}).click();
    await panel.getByLabel("选择学习伙伴").selectOption(id);
    await expect.poll(()=>state.account.preferences.companion_pet_id).toBe(id);
    await expect(sprite).toHaveAttribute("aria-label",name);
    await expect(sprite).toHaveCSS("width","104px");
    expect(await sprite.evaluate(element=>getComputedStyle(element).backgroundImage)).toContain(image);
    await expect(panel.getByRole("button",{name:"更多选项",exact:true})).toHaveAttribute("aria-expanded","false");
  }
  await panel.getByRole("button",{name:"收起对话",exact:true}).click();
  const bounds=(await toggle.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width / 2,bounds.y + bounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(360 + bounds.width / 2,280 + bounds.height / 2,{steps:12});
  await page.mouse.up();
  await expect.poll(async()=>Math.abs((await dock.boundingBox())!.x - 360)).toBeLessThan(2);
  await expect(panel).toHaveCount(0);
  await page.reload();
  await expect(sprite).toBeVisible();
  await expect.poll(async()=>Math.abs((await dock.boundingBox())!.x - 360)).toBeLessThan(2);
  await toggle.click();
  await expect(panel).toBeVisible();
});

async function learningFixture(page: Page, stage: string, questionType = "SINGLE_CHOICE") {
  const state=await fixture(page,{stage,interactive:true,interactivePurpose:"GAME"});
  let count=0;
  let submitted=false;
  let quizCreated=false;
  let position=0;
  let drafts:Record<string,{answer:unknown;revision:number}>={};
  const conversation={...session,chapter_id:null,chapter_title:null,stage,grade:state.account.profile.grade};
  const job=()=>({id:"inline-job",status:"SUCCEEDED",error_code:null,quiz_session_id:"inline-quiz",source_conversation_id:session.id,source_message_id:"quiz-request",fixture:true,request_summary:{topic:"让机器学会分类",count,generated_count:count}});
  const quiz=()=>({id:"inline-quiz",chapter_id:"chapter-ui",source_conversation_id:session.id,stage,status:"ACTIVE",source_kind:"AI_DRAFT",source_label:"合成示例",question_count:count,difficulty:"EASY",max_attempts:2,max_hints:3,current_position:position,drafts,progress:{answered:submitted?1:0,correct:submitted?1:0,total:count},notices:["合成示例，仅用于界面验证"],questions:Array.from({length:count},(_,index)=>({id:`q-${index}`,question_key:`q${index}`,position:index,type:"SINGLE_CHOICE",stem:`第 ${index+1} 道分类题：苹果的颜色属于什么？`,options:[{key:"A",text:"特征"},{key:"B",text:"答案"}],source_refs:[],hint_limit:0,hints_used:0,hints:[],attempts_used:index===0&&submitted?1:0,max_attempts:2,...(index===0&&submitted?{feedback:{is_correct:true,outcome:"CORRECT",correct_answer:"A",explanation:"颜色是用于描述样本的特征。",attempts_used:1,max_attempts:2}}:{})}))});
  const renderedQuiz = () => {
    const value = quiz();
    if (questionType !== "SINGLE_CHOICE") value.questions = value.questions.map(question => ({...question,type:questionType,
      options:questionType === "TRUE_FALSE" ? [{key:"TRUE",text:"对"},{key:"FALSE",text:"错"}] : [],
      items:questionType === "ORDERING" ? [{key:"first",text:"观察颜色"},{key:"second",text:"按颜色分类"}] : undefined,
    }));
    return value;
  };
  await page.route("**/api/v1/conversations**",async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    if(path==="/api/v1/conversations") return route.fulfill({json:request.method()==="POST"?conversation:[conversation]});
    if(path===`/api/v1/conversations/${session.id}`) return route.fulfill({json:{...conversation,messages:state.messages}});
    return route.fallback();
  });
  await page.route("**/api/v1/quiz-generation-jobs**",async route=>{
    const request=route.request();
    if(request.method()==="POST") {
      const body=request.postDataJSON();
      expect(body.conversation_id).toBe(session.id);
      expect(body.scene.chapter_id).toBe("chapter-ui");
      expect(body.scene.chapter_revision).toBe(1);
      count=body.ordinary_question_count; quizCreated=true;
      state.messages.push({id:"quiz-request",role:"USER",content_markdown:body.student_request,card:null,created_at:session.created_at});
      return route.fulfill({status:202,json:{job:job(),quiz:null}});
    }
    return route.fulfill({json:{items:quizCreated?[job()]:[],total:quizCreated?1:0}});
  });
  await page.route("**/api/v1/quiz-sessions/inline-quiz**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/draft")) {
      const body=route.request().postDataJSON();
      drafts["q-0"]={answer:body.answer,revision:(drafts["q-0"]?.revision??0)+1};
      return route.fulfill({json:{draft:drafts["q-0"]}});
    }
    if(path.endsWith("/answers")) { submitted=true; return route.fulfill({json:{is_correct:true,outcome:"CORRECT",correct_answer:"A",explanation:"颜色是特征。",progress:{answered:1,total:count},session_status:"ACTIVE"}}); }
    if(path.endsWith("/position")) { position=route.request().postDataJSON().position; return route.fulfill({json:{position}}); }
    return route.fulfill({json:renderedQuiz()});
  });
  return state;
}

for (const type of ["TRUE_FALSE","ORDERING"]) {
  test(`inline ${type} uses the existing answer controls and server feedback`,async({page})=>{
    await learningFixture(page,"SENIOR",type);
    await page.goto("/chapters/chapter-ui");
    await page.getByTestId("companion-dock").getByRole("button").click();
    const panel=page.locator("#companion-panel");
    await panel.getByRole("textbox").fill("给本章出1题");
    await panel.getByRole("button",{name:"发送",exact:true}).click();
    await expect(panel.getByTestId("inline-quiz")).toBeVisible();
    if(type === "TRUE_FALSE") await panel.getByLabel("对",{exact:true}).check();
    else await expect(panel.getByTestId("quiz-ordering")).toBeVisible();
    await expect(panel.getByRole("button",{name:"提交答案",exact:true})).toBeEnabled();
    await panel.getByRole("button",{name:"提交答案",exact:true}).click();
    await expect(panel.getByText("颜色是用于描述样本的特征。")).toBeVisible();
  });
}

for(const stage of ["PRIMARY_LOWER","PRIMARY_UPPER","JUNIOR","SENIOR"]) {
  for(const width of [320,390,768,1440]) {
    test(`${stage} ${width}px continuous dialogue generates ten questions and restores inline feedback`,async({page})=>{
      await page.setViewportSize({width,height:900});
      const state=await learningFixture(page,stage);
      const errors:string[]=[];
      page.on("pageerror",error=>errors.push(error.message));
      await page.goto("/chapters/chapter-ui");
      await expect(page.getByRole("link",{name:"进入本章课堂"})).toHaveCount(0);
      await page.getByTestId("companion-dock").getByRole("button").click();
      const panel=page.locator("#companion-panel");
      await expect(panel).toBeVisible();
      await panel.getByRole("button",{name:"更多学习操作",exact:true}).click();
      await page.getByRole("menuitem",{name:/生成练习/}).click();
      await expect(panel.getByRole("button",{name:"20 题"})).toBeVisible();
      await panel.getByRole("button",{name:"取消",exact:true}).click();
      await panel.getByRole("textbox").fill("给本章出 10 道题");
      await panel.getByRole("button",{name:"发送",exact:true}).click();
      await expect(panel.getByTestId("inline-quiz")).toBeVisible();
      await expect(panel.getByTestId("quiz-question-progress")).toContainText("1 / 10");
      await expect(panel.getByTestId("quiz-stem")).toBeInViewport();
      await panel.getByLabel("特征",{exact:true}).check();
      await panel.getByRole("button",{name:"提交答案",exact:true}).click();
      await expect(panel.getByText("颜色是用于描述样本的特征。")).toBeVisible();
      await page.screenshot({path:`test-results/companion-inline-${stage}-${width}.png`,animations:"disabled"});
      await panel.getByRole("button",{name:"收起对话",exact:true}).click();
      await page.reload();
      await page.getByTestId("companion-dock").getByRole("button").click();
      await expect(panel.getByText("颜色是用于描述样本的特征。")).toBeVisible();
      await panel.getByRole("button",{name:"下一题",exact:true}).click();
      await expect(panel.getByTestId("quiz-question-progress")).toContainText("2 / 10");
      await expect(panel.getByTestId("quiz-stem")).toBeInViewport();
      await panel.getByRole("button",{name:"收起对话",exact:true}).click();
      for(const route of ["/practice","/history","/growth","/settings","/onboarding","/conversations","/resources","/books/python3","/picturebooks","/animations","/interactive/interactive-ui","/code"]) {
        await page.goto(route);
        await expect(page.getByTestId("companion-dock")).toBeVisible();
        if(route==="/practice") {
          await expect(page.getByRole("heading",{name:"按章节练习"})).toHaveCount(0);
          await expect(page.getByRole("link",{name:"准备练习"})).toHaveCount(0);
        }
      }
      expect(state.starts).toBe(0);
      expect(errors).toEqual([]);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
  }
}

test("changing chapters keeps one conversation and preserves an unsent question",async({page})=>{
  const state=await learningFixture(page,"JUNIOR");
  const second={chapter_id:"chapter-two",course_id:"course-ui",course_slug:"computational-thinking",course_title:"计算思维",chapter_slug:"next",title:"新的章节",order_index:2,stage:"JUNIOR",revision:1,revision_id:"second-revision",is_test_fixture:true,content_notice:"合成示例",objectives:[],knowledge_points:[],source:{source_commit:"synthetic",source_path:"synthetic"},license_code:"SYNTHETIC",source_manifest:{},navigation:{prev:null,next:null},blocks:[{block_id:"b1",type:"TITLE",text:"新的章节"},{block_id:"b2",type:"PARAGRAPH",text:"这里讨论新的知识点。"}]};
  await page.route("**/api/v1/courses/course-ui",route=>route.fulfill({json:{course_id:"course-ui",slug:"computational-thinking",title:"计算思维",topic:"计算思维",description:"合成示例",chapters:[{...second,chapter_id:"chapter-ui",title:"让机器学会分类",order_index:1},second]}}));
  await page.route("**/api/v1/chapters/chapter-two**",route=>route.fulfill({json:route.request().url().includes("reading-state")?null:second}));
  await page.goto("/chapters/chapter-ui");
  await page.getByTestId("companion-dock").getByRole("button").click();
  const panel=page.locator("#companion-panel");
  await panel.getByRole("textbox").fill("给本章出5道题");
  await panel.getByRole("button",{name:"发送",exact:true}).click();
  await expect(panel.getByTestId("inline-quiz")).toBeVisible();
  await panel.getByRole("textbox").fill("这里我还有一点不明白");
  await panel.getByRole("button",{name:"收起对话",exact:true}).click();
  await page.locator('.reader-navigation a[href="/chapters/chapter-two"]').click();
  await expect(page.getByRole("heading",{name:"新的章节",exact:true})).toBeVisible();
  await page.getByTestId("companion-dock").getByRole("button").click();
  await expect(panel.getByRole("textbox")).toHaveValue("这里我还有一点不明白");
  await expect(panel.getByText("当前参考：新的章节",{exact:true})).toBeVisible();
  await expect(panel.getByTestId("inline-quiz")).toBeVisible();
  await expect(panel.getByRole("link",{name:"打开完整对话"})).toHaveAttribute("href",`/conversations?session=${session.id}`);
  expect(state.starts).toBe(0);
});

for(const stage of ["PRIMARY_LOWER","PRIMARY_UPPER","JUNIOR","SENIOR"]) {
  test(`${stage} composer plus menu and animated generation work at desktop and mobile widths`,async({page})=>{
    const state=await learningFixture(page,stage);
    let progress=0;
    const pending=()=>({id:"pending-ui",status:"RUNNING",error_code:null,quiz_session_id:null,source_message_id:"pending-request",fixture:true,request_summary:{topic:"让机器学会分类",count:10,generated_count:progress}});
    let created=false;
    await page.route("**/api/v1/quiz-generation-jobs**",async route=>{
      if(route.request().method()==="POST") {
        created=true;
        state.messages.push({id:"pending-request",role:"USER",content_markdown:"给本章出10题",card:null,created_at:session.created_at});
        return route.fulfill({status:202,json:{job:pending(),quiz:null}});
      }
      return route.fulfill({json:{items:created?[pending()]:[]}});
    });
    const errors:string[]=[];
    page.on("pageerror",error=>errors.push(error.message));
    await page.setViewportSize({width:1440,height:900});
    await page.goto("/chapters/chapter-ui");
    await page.getByTestId("companion-dock").getByRole("button").click();
    const panel=page.locator("#companion-panel");
    const trigger=panel.getByRole("button",{name:"更多学习操作",exact:true});
    for(const width of [1440,768,390,320]) {
      await page.setViewportSize({width,height:900});
      // Consume the asynchronous resize and panel layout before opening a menu
      // that intentionally closes on viewport changes.
      await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
      await expect(page.getByRole("menuitem",{name:/生成练习/})).toHaveCount(0);
      await trigger.press("ArrowDown");
      const menu=page.getByRole("menu",{name:"学习操作",exact:true});
      await expect(menu).toBeInViewport();
      await expect(menu.getByRole("menuitem",{name:/生成练习/})).toBeFocused();
      await expectMenuTextReadable(menu.getByRole("menuitem",{name:/生成练习/}));
      await menu.getByRole("menuitem",{name:/生成练习/}).press("ArrowDown");
      await expect(menu.getByRole("menuitem",{name:/解释这里/})).toBeFocused();
      await expectMenuTextReadable(menu.getByRole("menuitem",{name:/解释这里/}));
      for (const name of [/生成练习/,/解释这里/]) {
        const item=menu.getByRole("menuitem",{name});
        await item.hover();
        await expectMenuTextReadable(item);
      }
      await menu.getByRole("menuitem",{name:/生成练习/}).press("Home");
      await menu.getByRole("menuitem",{name:/生成练习/}).hover();
      await page.screenshot({path:`test-results/companion-composer-menu-${stage}-${width}.png`,animations:"disabled"});
      if(width===390) await menu.screenshot({path:`test-results/companion-menu-contrast-${stage}-390.png`,animations:"disabled"});
      await menu.getByRole("menuitem",{name:/解释这里/}).press("Escape");
      await expect(menu).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await expect(panel).toBeVisible();
      await trigger.click();
      await page.getByRole("menuitem",{name:/解释这里/}).click();
      await expect(panel.getByRole("textbox")).toHaveValue(/请结合.*让机器学会分类.*解释当前内容/);
      expect(state.turns).toBe(0);
      await expect(panel.getByTestId("send-turn")).toBeEnabled();
      await expect.poll(()=>panel.getByTestId("send-turn").evaluate(node=>getComputedStyle(node).backgroundColor)).toBe("rgb(52, 120, 246)");
      await page.screenshot({path:`test-results/companion-composer-draft-${stage}-${width}.png`,animations:"disabled"});
      await panel.getByRole("textbox").fill("");
      await expect(panel.getByTestId("send-turn")).toBeDisabled();
      const send=panel.getByTestId("send-turn");
      expect(await send.evaluate(node=>getComputedStyle(node).borderRadius)).toBe("50%");
      await trigger.click();
      await panel.getByRole("textbox").click();
      await expect(menu).toHaveCount(0);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await panel.getByRole("textbox").fill("给本章出10题");
    await panel.getByRole("button",{name:"发送",exact:true}).click();
    const meter=panel.getByRole("progressbar",{name:"题目生成进度"});
    await expect(meter).toHaveAttribute("aria-valuenow","0");
    const animation=panel.locator(".quiz-generation-pencil");
    expect(await animation.evaluate(node=>getComputedStyle(node).animationName)).toBe("quiz-pencil");
    await page.screenshot({path:`test-results/companion-generating-${stage}-320.png`});
    progress=5;
    await expect(meter).toHaveAttribute("aria-valuenow","5");
    await expect(meter).toHaveAttribute("aria-valuemax","10");
    await page.emulateMedia({reducedMotion:"reduce"});
    expect(await animation.evaluate(node=>getComputedStyle(node).animationName)).toBe("none");
    await page.screenshot({path:`test-results/companion-generating-${stage}-320-reduced-motion.png`});
    expect(errors).toEqual([]);
  });
}
