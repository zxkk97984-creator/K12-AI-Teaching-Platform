import {expect, test, type FrameLocator} from '@playwright/test';
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';

test.skip(process.env.K12_AUTOPLAY_EXAMPLES_E2E !== '1', 'Use the isolated learning browser script with K12_AUTOPLAY_EXAMPLES_E2E=1');
const catalog = JSON.parse(readFileSync(resolve(process.cwd(), '../k12-autoplay-examples-v1/catalog.json'), 'utf8')) as Array<{id:string; title:string; stage:string}>;

async function changeExperiment(frame: FrameLocator | import("@playwright/test").Page, id: string) {
  if(id.endsWith('input-process-output'))await frame.getByRole('button',{name:'按键 B',exact:true}).click();
  else if(id.endsWith('sorting-by-rule'))await frame.getByRole('button',{name:'按颜色分'}).click();
  else if(id.endsWith('robot-instructions'))await frame.getByRole('button',{name:'检查错误路线'}).click();
  else if(id.endsWith('pixels-build-picture'))await frame.getByRole('button',{name:'较细 8×8'}).click();
  else if(id.endsWith('cards-bubble-sort')){await frame.locator('#sort-input').fill('9,1,8,2,6');await frame.getByRole('button',{name:'运行排序'}).click();}
  else if(id.endsWith('message-packets'))await frame.getByRole('button',{name:'路线乙：1、2、3 到达'}).click();
  else if(id.endsWith('linear-search')){await frame.locator('#search-target').fill('99');await frame.getByRole('button',{name:'开始查找'}).click();}
  else if(id.endsWith('stack-and-queue')){await frame.getByRole('button',{name:'练习队列'}).click();await frame.getByRole('button',{name:'加入 A/B/C'}).click();await frame.getByRole('button',{name:'加入 A/B/C'}).click();await frame.getByRole('button',{name:'取出一个'}).click();}
  else if(id.endsWith('training-and-testing'))await frame.getByRole('button',{name:'测试点乙'}).click();
  else if(id.endsWith('shortest-path')){await frame.locator('#path-start').selectOption('B');await frame.locator('#path-end').selectOption('E');await frame.getByRole('button',{name:'计算路线'}).click();}
  else if(id.endsWith('gradient-descent')){await frame.locator('#alpha').selectOption('0.6');await frame.getByRole('button',{name:'比较 6 次更新'}).click();}
  else if(id.endsWith('classification-metrics')){await frame.locator('#threshold').fill('0.7');await frame.getByRole('button',{name:'重新计算'}).click();}
  else throw new Error('Unknown example '+id);
}

for (const stage of ['PRIMARY_LOWER','PRIMARY_UPPER','JUNIOR','SENIOR']) {
  test(`${stage}: imported autoplay examples use the real host, restore scenes and preserve manual practice`, async ({page, browser}) => {
    test.setTimeout(180000);
    const errors:string[]=[]; page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(() => {
      const nativeTimeout=window.setTimeout.bind(window);
      window.setTimeout=((handler:TimerHandler,delay?:number,...args:unknown[])=>nativeTimeout(handler,delay===650?40:delay,...args)) as typeof window.setTimeout;
      let activeTimer=0;
      class Speech {
        voice=null;lang='';rate=1;onstart?:()=>void;onend?:()=>void;
        constructor(public text:string){}
      }
      Object.defineProperty(window,'SpeechSynthesisUtterance',{configurable:true,value:Speech});
      Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{
        getVoices:()=>[{name:'Synthetic Mandarin host event test',lang:'zh-CN',voiceURI:'host-test',localService:true}],
        addEventListener(){},removeEventListener(){},resume(){},
        cancel(){clearTimeout(activeTimer);},
        speak(speech:Speech){speech.onstart?.();activeTimer=nativeTimeout(()=>speech.onend?.(),250);}
      }});
    });
    await page.goto('/login');
    await page.getByLabel('用户名',{exact:true}).fill('html.'+stage.toLowerCase());
    await page.getByLabel('密码',{exact:true}).fill('synthetic-html-pass-2026');
    await page.getByRole('button',{name:'登录并继续'}).click(); await expect(page).toHaveURL(/\/workbench$/);
    if(stage==='JUNIOR'||stage==='SENIOR'){
      await page.goto('/activities');await page.getByRole('button',{name:'动画讲解',exact:true}).click();
    }else await page.goto('/animations');
    const expected=catalog.filter(item=>item.stage===stage);
    for(const item of expected) await expect(page.getByRole('heading',{name:item.title,exact:true})).toBeVisible();
    const items=(await (await page.request.get('/api/v1/interactive/resources?purpose=LESSON')).json()).items as Array<{id:string;title:string;stage:string}>;
    for(const item of expected){
      const resource=items.find(row=>row.title===item.title)!; expect(resource).toBeTruthy();
      const csrf=(await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token;
      expect((await page.request.post('/api/v1/interactive/sessions',{data:{resource_id:resource.id,restart:true},headers:{Origin:new URL(page.url()).origin,'X-CSRF-Token':csrf}})).ok()).toBe(true);
      await page.goto(`/interactive/${resource.id}`);
      await page.getByRole('button',{name:/^(开始学习|继续学习)$/}).click();
      const frame=page.frameLocator('.interactive-stage iframe'); const player=page.getByTestId('interactive-player');
      await expect(frame.locator('body')).toHaveClass(/embedded/);
      if(stage!=='PRIMARY_LOWER')await page.getByTestId('lesson-autoplay').click();
      await expect.poll(async()=>Number(await player.getAttribute('data-playback-step'))).toBeGreaterThan(0);
      await page.getByRole('button',{name:'暂停播放',exact:true}).click();
      const index=await player.getAttribute('data-playback-step');
      await page.waitForTimeout(500);await expect(player).toHaveAttribute('data-playback-step',index!);
      await page.reload();await page.getByRole('button',{name:'继续学习',exact:true}).click();
      await expect(frame.locator('body')).toHaveClass(/embedded/);
      if(stage!=='PRIMARY_LOWER')await page.getByTestId('lesson-autoplay').click();
      await expect(player).toHaveAttribute('data-playback','ended',{timeout:30000});
      await expect(page.getByTestId('lesson-viewed')).toContainText('已看完');
      const content=(await (await page.request.get(`/api/v1/interactive/resources/${resource.id}`)).json()).manifest;
      await expect(frame.locator('#current-step')).toContainText(`第 ${content.scenes.length} 段`);
      for(const viewport of [{width:1920,height:940},{width:1366,height:768}]){
        await page.setViewportSize(viewport);
        await expect.poll(()=>frame.locator('html').evaluate(el=>{
          const viewer=el.querySelector('.viewer')!.getBoundingClientRect();
          return Math.abs(el.clientHeight-viewer.bottom-12);
        })).toBeLessThanOrEqual(2);
        const heights=await frame.locator('html').evaluate(el=>({canvas:el.querySelector('.canvas')!.getBoundingClientRect().height,svg:el.querySelector('.lesson-svg')!.getBoundingClientRect().height}));
        expect(heights.svg).toBeGreaterThan(heights.canvas-20);
      }
      mkdirSync('test-results/autoplay-examples-platform',{recursive:true});
      await page.screenshot({path:`test-results/autoplay-examples-platform/${item.id}-desktop.png`});
      if(item.id==='primary-lower-robot-instructions'){
        await page.getByRole('button',{name:'自己试一试',exact:true}).click();
        await page.getByLabel('当前课程环节').selectOption('scene-05');
        await expect(frame.locator('#current-step')).toContainText('第 5 段');
        await expect.poll(()=>frame.locator('#visual > svg').evaluate(image=>{
          const robot=image.querySelector('.robot-face')!.getBoundingClientRect();
          const target=image.querySelectorAll('.grid-cell')[3].getBoundingClientRect();
          return Math.hypot(robot.x+robot.width/2-target.x-target.width/2,robot.y+robot.height/2-target.y-target.height/2);
        })).toBeLessThan(2);
        const goalOffset=await frame.locator('#visual > svg').evaluate(image=>{
          const goal=Array.from(image.querySelectorAll('.map-label')).find(label=>label.textContent==='终点')!;
          const cell=image.querySelectorAll('.grid-cell')[4];
          const target=cell.getBoundingClientRect();
          return Math.abs(goal.getBoundingClientRect().x+goal.getBoundingClientRect().width/2-target.x-target.width/2);
        });
        expect(goalOffset).toBeLessThan(2);
        await page.getByTestId('lesson-autoplay').click();
        await expect(player).toHaveAttribute('data-playback','ended',{timeout:30000});
      }
      await page.getByRole('button',{name:'自己试一试',exact:true}).click();
      await expect(frame.locator('#practice-panel')).toBeVisible();
      await expect(frame.locator('#practice-controls button').first()).toBeEnabled();
      await changeExperiment(frame,item.id);
      await expect(page.locator('.interactive-player-header .interactive-status[role=status]')).toHaveText('已保存到账号');
      const result=await frame.locator('#practice-output').textContent();
      const picture=await frame.locator('#practice-visual').textContent();
      const before=(await (await page.request.get('/api/v1/interactive/sessions')).json()).items.find((row:{resource_id:string;status:string})=>row.resource_id===resource.id&&row.status==='ACTIVE');
      expect(before.viewed_at).toBeTruthy();expect(before.game_result).toBeNull();expect(before.game_state.practice.operated).toBe(true);
      await page.reload();await page.getByRole('button',{name:'继续学习',exact:true}).click();
      await expect(frame.locator('body')).toHaveClass(/embedded/);
      await page.getByRole('button',{name:'自己试一试',exact:true}).click();
      await expect(frame.locator('#practice-output')).toHaveText(result!);
      await expect(frame.locator('#practice-visual')).toHaveText(picture!);
      // Rewatch is allowed and must leave the experiment untouched.
      await page.getByTestId('lesson-autoplay').click();
      await expect(player).toHaveAttribute('data-playback','ended',{timeout:30000});
      await page.getByRole('button',{name:'自己试一试',exact:true}).click();
      await expect(frame.locator('#practice-output')).toHaveText(result!);
      const after=(await (await page.request.get(`/api/v1/interactive/sessions/${before.id}`)).json()).session;
      expect(after.game_state).toEqual(before.game_state);expect(after.viewed_at).toBe(before.viewed_at);
      const context=await browser.newContext();const other=await context.newPage();
      try{
        await other.goto(new URL('/login',page.url()).href);
        await other.getByLabel('用户名',{exact:true}).fill('html.'+stage.toLowerCase());await other.getByLabel('密码',{exact:true}).fill('synthetic-html-pass-2026');
        await other.getByRole('button',{name:'登录并继续'}).click();await expect(other).toHaveURL(/\/workbench$/);
        await other.goto(new URL(`/interactive/${resource.id}`,page.url()).href);await other.getByRole('button',{name:'继续学习',exact:true}).click();
        const restored=other.frameLocator('.interactive-stage iframe');await expect(restored.locator('body')).toHaveClass(/embedded/);
        await other.getByRole('button',{name:'自己试一试',exact:true}).click();await expect(restored.locator('#practice-output')).toHaveText(result!);
        await expect(restored.locator('#practice-visual')).toHaveText(picture!);
      }finally{await context.close();}
      await expect(frame.locator('#practice-error')).toHaveText('');
      for(const width of [1366,390,320]){
        await page.setViewportSize({width,height:width===320?568:width===390?844:768});
        expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
        if(width===390){
          await frame.locator('#practice-controls button').last().scrollIntoViewIfNeeded();
          await expect(frame.locator('#practice-controls button').last()).toBeInViewport();
          await page.screenshot({path:`test-results/autoplay-examples-platform/${item.id}-390.png`});
        }
        await expect.poll(()=>frame.locator('html').evaluate(el=>el.scrollWidth-el.clientWidth)).toBeLessThanOrEqual(1);
      }
      mkdirSync('test-results/autoplay-examples-platform',{recursive:true});
      await page.screenshot({path:`test-results/autoplay-examples-platform/${item.id}-320.png`});
      await page.setViewportSize({width:1366,height:768});
      await page.getByLabel('学习操作',{exact:true}).click();await page.getByRole('button',{name:'保存并退出'}).click();await expect(page).toHaveURL(/\/animations$/);
      await page.goto(`/interactive/${resource.id}`);await page.getByRole('button',{name:'继续学习',exact:true}).click();await expect(frame.locator('body')).toHaveClass(/embedded/);
      await page.getByRole('button',{name:'自己试一试',exact:true}).click();await expect(frame.locator('#practice-output')).toHaveText(result!);
    }
    expect(errors).toEqual([]);
  });
}

test('imported autoplay examples: failed saves, late receipts, two windows, accounts and viewed retry', async ({page,browser}) => {
  test.setTimeout(120000);
  await page.addInitScript(() => {
    let timer=0;
    class Speech {lang='';rate=1;voice=null;onstart?:()=>void;onend?:()=>void;constructor(public text:string){}}
    Object.defineProperty(window,'SpeechSynthesisUtterance',{configurable:true,value:Speech});
    Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>[{name:'Event fixture',lang:'zh-CN',voiceURI:'a6-event-fixture',localService:true}],addEventListener(){},removeEventListener(){},resume(){},cancel(){clearTimeout(timer);},speak(s:Speech){s.onstart?.();timer=window.setTimeout(()=>s.onend?.(),120);}}});
  });
  const login=async (target:typeof page, name:string) => {
    await target.goto(new URL('/login',page.url().startsWith('http')?page.url():test.info().project.use.baseURL).href);
    await target.getByLabel('用户名',{exact:true}).fill(name);await target.getByLabel('密码',{exact:true}).fill('synthetic-html-pass-2026');
    await target.getByRole('button',{name:'登录并继续'}).click();await expect(target).toHaveURL(/\/workbench$/);
  };
  await login(page,'html.primary_upper');
  const origin=new URL(page.url()).origin;
  const resource=(await (await page.request.get('/api/v1/interactive/resources?purpose=LESSON')).json()).items.find((item:{title:string})=>item.title==='数字卡片怎样排整齐');
  const headers={'Origin':origin,'X-CSRF-Token':(await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token};
  const start=(await page.request.post('/api/v1/interactive/sessions',{data:{resource_id:resource.id,restart:true},headers})).json();
  const activity=await start;
  const read=async()=> (await (await page.request.get(`/api/v1/interactive/sessions/${activity.id}`)).json()).session;
  await page.goto(`/interactive/${resource.id}`);await page.getByRole('button',{name:'开始学习',exact:true}).click();
  const frame=page.frameLocator('.interactive-stage iframe');await expect(frame.locator('body')).toHaveClass(/embedded/);
  await page.getByRole('button',{name:'自己试一试',exact:true}).click();
  let fail=true;
  await page.route('**/interactive/sessions/*/checkpoint',async route=>{if(fail){fail=false;await route.fulfill({status:503,contentType:'application/json',body:'{"detail":"保存暂不可用"}'});}else await route.continue();});
  await changeExperiment(frame,'primary-upper-cards-bubble-sort');
  await expect(page.getByRole('button',{name:'重试保存'})).toBeVisible();
  const retained=await frame.locator('#practice-output').textContent();
  await frame.locator('#sort-input').fill('bad');await frame.getByRole('button',{name:'运行排序'}).click();
  await expect(frame.locator('#practice-error')).toContainText('原有结果已保留');await expect(frame.locator('#practice-output')).toHaveText(retained!);
  expect((await read()).game_state).toEqual({});
  await page.getByRole('button',{name:'重试保存'}).click();await expect(frame.locator('#practice-save-status')).toHaveText('实验已保存到账号');
  await page.unroute('**/interactive/sessions/*/checkpoint');
  let release!:()=>void, received!:()=>void;const gate=new Promise<void>(done=>{release=done;});const started=new Promise<void>(done=>{received=done;});let hold=true;
  await page.route('**/interactive/sessions/*/checkpoint',async route=>{if(hold){hold=false;const response=await route.fetch();received();await gate;await route.fulfill({response});}else await route.continue();});
  await frame.locator('#sort-input').fill('8,3,1');await frame.getByRole('button',{name:'运行排序'}).click();await started;
  await frame.locator('#sort-input').fill('7,4,2');await frame.getByRole('button',{name:'运行排序'}).click();
  await expect(frame.locator('#practice-output')).toContainText('[2, 4, 7]');release();
  await expect.poll(async()=> (await read()).game_state.practice.values).toEqual([7,4,2]);await expect(frame.locator('#practice-output')).toContainText('[2, 4, 7]');
  await page.unroute('**/interactive/sessions/*/checkpoint');
  const context=await browser.newContext();const other=await context.newPage();
  try{
    await login(other,'html.primary_upper');await other.goto(`${origin}/interactive/${resource.id}`);await other.getByRole('button',{name:'继续学习',exact:true}).click();
    const remote=other.frameLocator('.interactive-stage iframe');await expect(remote.locator('body')).toHaveClass(/embedded/);await other.getByRole('button',{name:'自己试一试',exact:true}).click();
    await remote.locator('#sort-input').fill('6,5,4');await remote.getByRole('button',{name:'运行排序'}).click();await expect.poll(async()=> (await read()).game_state.practice.values).toEqual([6,5,4]);
    await frame.locator('#sort-input').fill('1,9,3');await frame.getByRole('button',{name:'运行排序'}).click();await expect(page.getByRole('button',{name:'读取远端记录'})).toBeVisible();
    await expect(frame.locator('#practice-output')).toContainText('[1, 3, 9]');
    await page.getByLabel('学习操作',{exact:true}).click();await page.getByRole('button',{name:'保存并退出'}).click();await expect(page).toHaveURL(new RegExp('/interactive/'+resource.id));await expect(frame.locator('#practice-output')).toContainText('[1, 3, 9]');
    page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'读取远端记录'}).click();await page.getByRole('button',{name:'继续学习',exact:true}).click();await expect(frame.locator('body')).toHaveClass(/embedded/);await page.getByRole('button',{name:'自己试一试',exact:true}).click();await expect(frame.locator('#practice-output')).toContainText('[4, 5, 6]');
    // The same browser can sign into a second account without inheriting the first state.
    await login(other,'html.primary_lower');const me=(await (await other.request.get('/api/v1/me')).json());
    const otherHeaders={Origin:origin,'X-CSRF-Token':(await (await other.request.get('/api/v1/auth/csrf')).json()).csrf_token};
    expect((await other.request.patch('/api/v1/me/profile',{headers:otherHeaders,data:{base_revision:me.profile.revision,stage:'PRIMARY_UPPER',grade:4}})).ok()).toBe(true);
    try{
      expect((await other.request.get(`/api/v1/interactive/sessions/${activity.id}`)).status()).toBe(404);
      const own=(await (await other.request.post('/api/v1/interactive/sessions',{headers:otherHeaders,data:{resource_id:resource.id,restart:true}})).json());expect(own.game_state).toEqual({});expect(own.viewed_at).toBeNull();
      await other.goto(`${origin}/interactive/${resource.id}`);await other.getByRole('button',{name:'开始学习',exact:true}).click();await expect(remote.locator('body')).toHaveClass(/embedded/);await other.getByRole('button',{name:'自己试一试',exact:true}).click();await expect(remote.locator('#practice-output')).toHaveText('选择一个操作，观察结果。');
    }finally{
      const updated=(await (await other.request.get('/api/v1/me')).json());await other.request.patch('/api/v1/me/profile',{headers:otherHeaders,data:{base_revision:updated.profile.revision,stage:me.profile.stage,grade:me.profile.grade}});
    }
  }finally{await context.close();}
  // Manual last-scene narration cannot create the independent viewing record.
  const manifest=(await (await page.request.get(`/api/v1/interactive/resources/${resource.id}`)).json()).manifest;
  await page.getByLabel('当前课程环节').selectOption(manifest.scenes.at(-1).id);await page.waitForTimeout(1000);expect((await read()).viewed_at).toBeNull();
  let failViewed=true;await page.route('**/interactive/sessions/*/viewed',async route=>{if(failViewed){failViewed=false;await route.fulfill({status:503,contentType:'application/json',body:'{"detail":"观看记录暂不可用"}'});}else await route.continue();});
  await page.getByTestId('lesson-autoplay').click();await expect(page.getByTestId('interactive-player')).toHaveAttribute('data-playback','ended',{timeout:30000});
  await expect(page.getByRole('button',{name:'重试保存'})).toBeVisible();expect((await read()).viewed_at).toBeNull();
  await page.getByRole('button',{name:'重试保存'}).click();await expect(page.getByTestId('lesson-viewed')).toContainText('已看完');
  await page.getByRole('button',{name:'自己试一试',exact:true}).click();await frame.locator('#sort-input').fill('3,8,2');await frame.getByRole('button',{name:'运行排序'}).click();await expect.poll(async()=> (await read()).game_state.practice.values).toEqual([3,8,2]);
  const viewed=(await read()).viewed_at;await page.getByTestId('lesson-autoplay').click();await expect(page.getByTestId('interactive-player')).toHaveAttribute('data-playback','ended',{timeout:30000});expect((await read()).viewed_at).toBe(viewed);
});


test('imported autoplay examples: twelve independent offline experiments', async ({page}) => {
  const {pathToFileURL}=await import('node:url');const errors:string[]=[];const requests:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
  const source=JSON.parse(readFileSync(resolve('../k12-autoplay-examples-v1/catalog.json'),'utf8')) as Array<{id:string;standalone_html:string;title:string}>;
  for(const item of source){
    await page.goto(pathToFileURL(resolve('../k12-autoplay-examples-v1',item.standalone_html)).href);await expect(page).toHaveTitle(item.title+' · 霜铃 K12');
    await page.locator('#begin').click();await page.locator('#practice-toggle').click();await changeExperiment(page,item.id);await expect(page.locator('#practice-error')).toHaveText('');
    await expect(page.locator('#practice-save-status')).toContainText('未保存到账号');
    if(item.id.endsWith('cards-bubble-sort')){
      await page.setViewportSize({width:1366,height:768});await page.locator('#sort-input').fill('9,0,9,1,2,3');await page.getByRole('button',{name:'运行排序'}).click();
      await expect(page.locator('#practice-output')).toContainText('[0, 1, 2, 3, 9, 9]');
      expect(await page.locator('#practice-visual .number-card').evaluateAll(nodes=>nodes.every(el=>{const box=(el as SVGGraphicsElement).getBBox();return box.x>=0&&box.x+box.width<=960;}))).toBe(true);
    }
    await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
  }
  expect(requests).toEqual([]);expect(errors).toEqual([]);
});


test('imported autoplay examples: original package stays pinned when a new revision is published', async ({page,browser}) => {
  test.setTimeout(90000);
  const {execFileSync}=await import('node:child_process');const oldRoot=resolve('test-results/a6-legacy/k12-autoplay-examples-v1');
  mkdirSync(resolve(oldRoot,'source'),{recursive:true});
  // The published content baseline contains the same legacy sources as the local workflow tag.
  for(const name of ['build.py','runtime.js','embedded.css'])writeFileSync(resolve(oldRoot,'source',name),execFileSync('git',['show',`97d25e280de61d9437cb6318b40f99ec3ae97423:k12-autoplay-examples-v1/source/${name}`]));
  execFileSync('python3',[resolve(oldRoot,'source/build.py')]);
  await page.addInitScript(()=>{
    let timer=0;class Speech{lang='';rate=1;voice=null;onstart?:()=>void;onend?:()=>void;constructor(public text:string){}}
    Object.defineProperty(window,'SpeechSynthesisUtterance',{configurable:true,value:Speech});
    Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>[{name:'Legacy event fixture',lang:'zh-CN',voiceURI:'a6-legacy-events',localService:true}],addEventListener(){},removeEventListener(){},resume(){},cancel(){clearTimeout(timer);},speak(s:Speech){s.onstart?.();timer=window.setTimeout(()=>s.onend?.(),120);}}});
  });
  await page.goto('/login');await page.getByLabel('用户名',{exact:true}).fill('html.primary_upper');await page.getByLabel('密码',{exact:true}).fill('synthetic-html-pass-2026');await page.getByRole('button',{name:'登录并继续'}).click();await expect(page).toHaveURL(/\/workbench$/);
  const origin=new URL(page.url()).origin;
  const resource=(await (await page.request.get('/api/v1/interactive/resources?purpose=LESSON')).json()).items.find((item:{title:string})=>item.title==='小方格怎样组成一张图片');
  const adminContext=await browser.newContext();const admin=await adminContext.newPage();
  try{
    await admin.goto(`${origin}/login`);await admin.getByLabel('用户名',{exact:true}).fill('html.bundle.admin');await admin.getByLabel('密码',{exact:true}).fill('synthetic-html-pass-2026');await Promise.all([admin.waitForResponse(r=>r.url().endsWith('/api/v1/auth/login')&&r.request().method()==='POST').then(r=>expect(r.ok()).toBe(true)),admin.getByRole('button',{name:'登录并继续'}).click()]);
    const headers={Origin:origin,'X-CSRF-Token':(await (await admin.request.get(`${origin}/api/v1/auth/csrf`)).json()).csrf_token};
    const versions=`${origin}/api/v1/admin/resources/${resource.id}/interactive-revisions`;
    const upload=async(path:string)=>{
      const response=await admin.request.post(versions,{headers:{...headers,'Content-Type':'application/zip','X-Filename':'pixels.zip'},data:readFileSync(path)});expect(response.ok(),await response.text()).toBe(true);
      const version=(await response.json());expect((await admin.request.post(`${versions}/${version.id}/activate`,{headers,data:{}})).ok()).toBe(true);return version;
    };
    const old=await upload(resolve(oldRoot,'packages/primary-upper-pixels-build-picture.zip'));expect(old.capabilities).toEqual(['SCENES']);
    const studentHeaders={Origin:origin,'X-CSRF-Token':(await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token};
    const oldSession=(await (await page.request.post('/api/v1/interactive/sessions',{headers:studentHeaders,data:{resource_id:resource.id,restart:true}})).json());expect(oldSession.revision_id).toBe(old.id);
    const current=await upload(resolve('../k12-autoplay-examples-v1/packages/primary-upper-pixels-build-picture.zip'));expect(current.capabilities).toContain('CHECKPOINTS');
    await page.goto(`/interactive/${resource.id}`);await page.getByRole('button',{name:'开始学习',exact:true}).click();
    const frame=page.frameLocator('.interactive-stage iframe');await expect(frame.locator('body')).toHaveClass(/embedded/);
    await page.getByTestId('lesson-autoplay').click();await expect(page.getByTestId('interactive-player')).toHaveAttribute('data-playback','ended',{timeout:30000});
    await page.getByRole('button',{name:'自己试一试',exact:true}).click();await frame.getByRole('button',{name:'较细 8×8'}).click();
    await expect(frame.locator('#practice-output')).toContainText('8×8');
    const pinned=(await (await page.request.get(`/api/v1/interactive/sessions/${oldSession.id}`)).json()).session;expect(pinned.revision_id).toBe(old.id);expect(pinned.game_state).toEqual({});
    await page.reload();await page.getByRole('button',{name:'继续学习',exact:true}).click();await expect(frame.locator('body')).toHaveClass(/embedded/);
    const restarted=(await (await page.request.post('/api/v1/interactive/sessions',{headers:studentHeaders,data:{resource_id:resource.id,restart:true}})).json());expect(restarted.revision_id).toBe(current.id);
    expect((await (await page.request.get(`/api/v1/interactive/sessions/${oldSession.id}`)).json()).session.revision_id).toBe(old.id);
  }finally{await adminContext.close();}
});
