import {test, expect, type Page, type FrameLocator} from '@playwright/test';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {mkdir} from 'node:fs/promises';

const evidence = 'test-results/ai-fruit-trainer';
const standalone = pathToFileURL(resolve('../curriculum/interactive/computing-ai-v1/ai-fruit-trainer/index.html')).href;
type Game = Page | FrameLocator;
async function label(game: Game, id: string, value: 'apple' | 'banana') {
  await game.locator(`[data-card="${id}"]`).click();
  await game.locator(`[data-label="${value}"]`).click();
}
async function first(game: Game, alreadyOne = false) {
  if (!alreadyOne) await label(game,'r1','apple');
  await label(game,'r2','apple');await label(game,'b1','banana');await label(game,'b2','banana');
  await game.locator('#test').click();await expect(game.locator('#feedback')).toContainText('挑战成功');
  await game.locator('#next').click();await expect(game.locator('#mission-title')).toHaveText('帮机器人见多识广');
  await expect(game.locator('#test')).toBeEnabled();
}
async function second(game: Game) {
  await game.locator('#test').click();await expect(game.locator('#test-cards')).toContainText('再看看：其实是苹果');
  await label(game,'y1','apple');await label(game,'g1','apple');await label(game,'g2','banana');
  await game.locator('#test').click();await expect(game.locator('#feedback')).toContainText('从 2 / 3 到 3 / 3');
  await game.locator('#next').click();await expect(game.locator('#mission-title')).toContainText('检查一下');await expect(game.locator('#test')).toBeEnabled();
}
async function third(game: Game) {
  await game.locator('#test').click();await expect(game.locator('#feedback')).toContainText('2 / 3');
  await label(game,'y1','apple');await game.locator('#test').click();await expect(game.locator('#feedback')).toContainText('标签改对了');
  await game.locator('#next').click();await expect(game.locator('#celebration')).toBeVisible();await expect(game.locator('#finish')).toBeEnabled();
}
async function hostSaved(page: Page) {await expect(page.locator('.interactive-player-header .interactive-status')).toHaveText('已保存到账号');}

for (const viewport of [{width:1440,height:900},{width:1024,height:768},{width:768,height:1024},{width:320,height:718}]) {
  test(`AI game standalone ${viewport.width}px: offline, keyboard, reduced motion and layout`, async ({page}) => {
    const errors: string[] = [];page.on('pageerror',error=>errors.push(error.message));
    const network: string[] = [];page.on('request',request=>{if (/^https?:/.test(request.url()))network.push(request.url());});
    await mkdir(evidence,{recursive:true});await page.setViewportSize(viewport);await page.emulateMedia({reducedMotion:'reduce'});await page.goto(standalone);
    await expect(page).toHaveTitle('训练小小 AI · 水果分类员');await expect(page.locator('#mission-title')).toHaveText('教机器人认水果');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await page.locator('.robot').evaluate(element=>getComputedStyle(element).animationName)).toBe('none');
    await page.locator('#test').click();await expect(page.locator('#feedback')).toContainText('还没有学习样例');
    await page.locator('[data-card="r1"]').focus();await page.keyboard.press('Enter');await page.keyboard.press('1');
    await expect(page.locator('[data-card="r1"]')).toContainText('标签：苹果');
    await first(page,true);await page.locator('#test').click();
    await page.screenshot({path:`${evidence}/standalone-${viewport.width}.png`,fullPage:true});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await label(page,'y1','apple');await label(page,'g1','apple');await label(page,'g2','banana');await page.locator('#test').click();await page.locator('#next').click();
    await expect(page.locator('#mission-title')).toContainText('检查一下');await expect(page.locator('#test')).toBeEnabled();await third(page);
    await expect(page.locator('#finish-note')).toHaveText('点击领取徽章，确认完成。');await page.locator('#finish').click();await expect(page.locator('#finish-note')).toContainText('本次挑战已完成');
    await page.locator('#restart-all').click();await expect(page.getByRole('dialog')).toBeVisible();await page.locator('#reset-cancel').click();await expect(page.locator('#celebration')).toBeVisible();
    await page.locator('#restart-all').click();await page.locator('#reset-confirm').click();await expect(page.locator('#mission-title')).toHaveText('教机器人认水果');
    await expect(page.locator('#sample-count')).toHaveText('已贴标签 0 / 4');expect(network).toEqual([]);expect(errors).toEqual([]);
  });
}

test('AI game platform: catalog, failed save, restore, teacher, badge and account history', async ({page}) => {
  test.skip(process.env.HTML_LEARNING_E2E !== '1','Use scripts/test-learning-browser.sh with the isolated database');
  test.setTimeout(120000);await mkdir(evidence,{recursive:true});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setViewportSize({width:1440,height:900});await page.goto('/login');
  await page.getByLabel('用户名',{exact:true}).fill('html.primary_lower');await page.getByLabel('密码',{exact:true}).fill('synthetic-html-pass-2026');await page.getByRole('button',{name:'登录并继续'}).click();await expect(page).toHaveURL(/\/workbench$/);
  const catalog=await (await page.request.get('/api/v1/interactive/resources?purpose=GAME')).json();
  const resource=catalog.items.find((item:{title:string})=>item.title==='训练小小 AI·水果分类员');expect(resource).toBeTruthy();
  const csrf=(await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token;
  await page.request.post('/api/v1/interactive/sessions',{data:{resource_id:resource.id,restart:true},headers:{Origin:new URL(page.url()).origin,'X-CSRF-Token':csrf}});
  await page.goto('/practice');await expect(page.getByRole('heading',{name:'训练小小 AI·水果分类员',exact:true})).toBeVisible();
  await page.screenshot({path:`${evidence}/platform-catalog.png`});
  await page.locator(`a[href="/interactive/${resource.id}?from=practice"]`).click();await page.getByRole('button',{name:'继续学习',exact:true}).or(page.getByRole('button',{name:'开始学习',exact:true})).click();
  const game=page.frameLocator('.interactive-stage iframe');await expect(game.locator('body')).toHaveClass(/embedded/);
  await expect(game.locator('#mission-title')).toHaveText('教机器人认水果');
  await page.screenshot({path:`${evidence}/platform-start.png`});
  let failOnce=true;
  await page.route('**/interactive/sessions/*/checkpoint',async route=>{if(failOnce){failOnce=false;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'测试：暂时无法保存'})});}else await route.continue();});
  await label(game,'r1','apple');await expect(game.locator('#retry-save')).toBeVisible();await expect(game.locator('[data-card="r1"]')).toContainText('标签：苹果');
  await game.locator('#retry-save').click();await hostSaved(page);await page.unroute('**/interactive/sessions/*/checkpoint');
  await page.reload();await page.getByRole('button',{name:'继续学习',exact:true}).click();await expect(game.locator('[data-card="r1"]')).toContainText('标签：苹果');
  await first(game,true);await game.locator('#test').click();await hostSaved(page);await page.screenshot({path:`${evidence}/platform-mistake.png`});
  await page.reload();await page.getByRole('button',{name:'继续学习',exact:true}).click();await expect(game.locator('#mission-title')).toHaveText('帮机器人见多识广');await expect(game.locator('#feedback')).toContainText('2 / 3');
  for (const viewport of [{width:768,height:1024},{width:320,height:718},{width:1440,height:900}]) {
    await page.setViewportSize(viewport);await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect.poll(()=>game.locator('body').evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:`${evidence}/platform-${viewport.width}.png`});
  }
  await page.getByRole('button',{name:'问老师',exact:true}).click();await expect(page.locator('.companion-panel')).toBeVisible();
  await page.keyboard.press('Escape');await expect(page.locator('.companion-panel')).toHaveCount(0);await expect(game.locator('#mission-title')).toHaveText('帮机器人见多识广');
  await second(game);await third(game);await hostSaved(page);await page.screenshot({path:`${evidence}/platform-badge.png`});
  const before=(await (await page.request.get('/api/v1/interactive/resources?purpose=GAME')).json()).items.find((item:{id:string})=>item.id===resource.id);
  expect(before.activity_status).toBe('ACTIVE');await game.locator('#finish').click();await expect(page.getByRole('heading',{name:'本次活动已完成'})).toBeVisible();
  const sessions=(await (await page.request.get('/api/v1/interactive/sessions')).json()).items;
  expect(sessions.find((session:{id:string})=>session.id===before.session_id)).toMatchObject({status:'COMPLETED',game_result:{score:3,maxScore:3,badge:'AI 小训练员'}});
  await page.goto('/practice');await expect(page.locator('.interactive-card').filter({hasText:'训练小小 AI·水果分类员'})).toContainText('已完成');
  await page.screenshot({path:`${evidence}/platform-completed.png`});expect(errors).toEqual([]);
});

test('AI game compact controls: canvas space, popovers, keyboard and responsive layout', async ({page}) => {
  test.skip(process.env.HTML_LEARNING_E2E !== '1','Use scripts/test-learning-browser.sh with the isolated database');
  test.setTimeout(90000);await mkdir(evidence,{recursive:true});const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setViewportSize({width:1542,height:718});await page.goto('/login');
  await page.getByLabel('用户名',{exact:true}).fill('html.primary_lower');await page.getByLabel('密码',{exact:true}).fill('synthetic-html-pass-2026');await page.getByRole('button',{name:'登录并继续'}).click();await expect(page).toHaveURL(/\/workbench$/);
  const resource=(await (await page.request.get('/api/v1/interactive/resources?purpose=GAME')).json()).items.find((item:{title:string})=>item.title==='训练小小 AI·水果分类员');
  const csrf=(await (await page.request.get('/api/v1/auth/csrf')).json()).csrf_token;
  const response=await page.request.post('/api/v1/interactive/sessions',{data:{resource_id:resource.id,restart:true},headers:{Origin:new URL(page.url()).origin,'X-CSRF-Token':csrf}});expect(response.ok()).toBe(true);
  await page.goto(`/interactive/${resource.id}?from=practice`);await page.getByRole('button',{name:'开始学习',exact:true}).click();
  const game=page.frameLocator('.interactive-stage iframe'),settings=page.locator('.interactive-voice-settings'),footer=page.locator('.interactive-control-area');
  await expect(game.locator('body')).toHaveClass(/embedded/);await expect(page.locator('#interactive-guide')).toBeHidden();
  await expect(settings).not.toHaveAttribute('open');await expect(page.getByLabel('朗读声音',{exact:true})).toBeHidden();
  const height=await page.locator('.interactive-stage').evaluate(element=>element.getBoundingClientRect().height);
  expect(height).toBeGreaterThan(480);expect(await footer.evaluate(element=>element.getBoundingClientRect().height)).toBeLessThanOrEqual(66);
  await page.screenshot({path:`${evidence}/compact-desktop.png`});
  await game.locator('[data-card="r1"]').click();await expect(game.locator('[data-card="r1"]')).toHaveAttribute('aria-pressed','true');
  await settings.locator('summary').click();await expect(page.getByLabel('朗读声音',{exact:true})).toBeVisible();
  expect(await page.locator('.interactive-stage').evaluate(element=>element.getBoundingClientRect().height)).toBe(height);
  await page.getByLabel('朗读语速',{exact:true}).selectOption('0.8');await expect(game.locator('[data-card="r1"]')).toHaveAttribute('aria-pressed','true');
  await page.screenshot({path:`${evidence}/compact-settings-desktop.png`});await page.keyboard.press('Escape');await expect(settings).not.toHaveAttribute('open');await expect(settings.locator('summary')).toBeFocused();
  await settings.locator('summary').click();await page.locator('.interactive-more > summary').click();
  await expect(settings).not.toHaveAttribute('open');await expect(page.locator('.interactive-more')).toHaveAttribute('open');
  await page.getByRole('heading',{name:'训练小小 AI·水果分类员',exact:true}).click();await expect(page.locator('.interactive-more')).not.toHaveAttribute('open');
  for(const viewport of [{width:1024,height:768},{width:768,height:1024},{width:390,height:844},{width:320,height:718}]) {
    await page.setViewportSize(viewport);await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await expect.poll(()=>game.locator('body').evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(await footer.evaluate(element=>element.getBoundingClientRect().height)).toBeLessThanOrEqual(90);
    await page.screenshot({path:`${evidence}/compact-${viewport.width}.png`});
    await settings.locator('summary').click();await expect(page.getByLabel('朗读声音',{exact:true})).toBeVisible();
    const bounds=await page.locator('.interactive-voice-settings-content').evaluate(element=>{const r=element.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:innerWidth,height:innerHeight};});
    expect(bounds.left).toBeGreaterThanOrEqual(0);expect(bounds.right).toBeLessThanOrEqual(bounds.width);expect(bounds.top).toBeGreaterThanOrEqual(0);expect(bounds.bottom).toBeLessThanOrEqual(bounds.height);
    await page.screenshot({path:`${evidence}/compact-settings-${viewport.width}.png`});await page.keyboard.press('Escape');await expect(settings).not.toHaveAttribute('open');
    await page.locator('.interactive-more > summary').click();await expect(page.getByRole('button',{name:'保存并退出',exact:true})).toBeVisible();await page.keyboard.press('Escape');
  }
  await page.setViewportSize({width:1542,height:718});await page.getByRole('button',{name:'本步讲解',exact:true}).click();await expect(page.locator('#interactive-guide')).toBeVisible();
  await page.getByRole('button',{name:'收起讲解',exact:true}).click();await expect(page.locator('#interactive-guide')).toBeHidden();
  await expect(game.locator('[data-card="r1"]')).toHaveAttribute('aria-pressed','true');expect(errors).toEqual([]);
});
