import {expect, test} from '@playwright/test';
import {readFileSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';

test.skip(process.env.K12_AUTOPLAY_EXAMPLES_E2E !== '1', 'Use the isolated learning browser script with K12_AUTOPLAY_EXAMPLES_E2E=1');
const catalog = JSON.parse(readFileSync(resolve(process.cwd(), '../k12-autoplay-examples-v1/catalog.json'), 'utf8')) as Array<{id:string; title:string; stage:string}>;
for (const stage of ['PRIMARY_LOWER','PRIMARY_UPPER','JUNIOR','SENIOR']) {
  test(`${stage}: imported autoplay examples use the real host, restore scenes and preserve manual practice`, async ({page}) => {
    test.setTimeout(120000);
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
      await frame.locator('#practice-controls button').first().click();
      await expect(frame.locator('#practice-error')).toHaveText('');
      for(const width of [1366,390,320]){
        await page.setViewportSize({width,height:width===320?568:width===390?844:768});
        expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
        await expect.poll(()=>frame.locator('html').evaluate(el=>el.scrollWidth-el.clientWidth)).toBeLessThanOrEqual(1);
      }
      mkdirSync('test-results/autoplay-examples-platform',{recursive:true});
      await page.screenshot({path:`test-results/autoplay-examples-platform/${item.id}-320.png`});
      await page.setViewportSize({width:1366,height:768});
    }
    expect(errors).toEqual([]);
  });
}
