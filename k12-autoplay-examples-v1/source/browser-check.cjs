#!/usr/bin/env node
/* Development-only real-browser verification. The lessons themselves need no Node or Playwright. */
'use strict';
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const playwrightPath = process.env.PLAYWRIGHT_PATH || '/usr/lib/chatgpt/resources/cua_node/lib/node_modules/playwright';
const { chromium } = require(playwrightPath);
const root = path.resolve(__dirname, '..');
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'catalog.json'), 'utf8'));
const shotDir = path.join(root, 'test-results', 'screenshots');
fs.mkdirSync(shotDir, { recursive: true });
const sizes = [[320,568],[390,844],[768,1024],[1366,768]];
const targets = {
  'primary-lower-input-process-output':[5,7],
  'primary-lower-sorting-by-rule':[4,7],
  'primary-lower-robot-instructions':[7,8],
  'primary-upper-pixels-build-picture':[4,7],
  'primary-upper-cards-bubble-sort':[2,12],
  'primary-upper-message-packets':[5,7],
  'junior-linear-search':[5,11],
  'junior-stack-and-queue':[5,11],
  'junior-training-and-testing':[8,10],
  'senior-shortest-path':[8,10],
  'senior-gradient-descent':[8,11,12],
  'senior-classification-metrics':[11,21,22],
};
const failures=[];
const entries=[];
let checkCount=0;
function verify(condition, message, key) {
  checkCount++;
  if (!condition) failures.push({sample:key||null,message});
}
function syntheticSpeechScript({voices=true, accelerateSilent=false}={}) {
  return `(() => {
    const rawTimeout = window.setTimeout.bind(window);
    window.__synthetic = {starts:0,ends:0,active:0,maxActive:0,speakCalls:0,cancelCalls:0};
    window.__testHoldStep = null; window.__testRelease = true; window.__testEventDelay = 180;
    window.__testAccelerateSilent = ${accelerateSilent}; window.__testAccelerateGap = true;
    window.setTimeout = function(fn, delay, ...args) {
      let ms = Number(delay) || 0;
      if (window.__testAccelerateSilent && (ms === 700 || ms >= 1000)) ms = 3;
      else if (window.__testAccelerateGap && ms === 700) ms = 5;
      return rawTimeout(fn, ms, ...args);
    };
    Object.defineProperty(window, 'SpeechSynthesisUtterance', {configurable:true,value:class TestUtterance { constructor(text){this.text=text;this.lang='';this.voice=null;this.rate=1;this.onstart=null;this.onend=null;this.onerror=null;} }});
    let generation=0; const timers=new Set();
    const shim={
      getVoices:()=>${voices ? `[{lang:'zh-CN',name:'Synthetic Mandarin Event Test'}]` : `[]`},
      addEventListener:()=>{}, removeEventListener:()=>{},
      cancel:()=>{window.__synthetic.cancelCalls++;generation++;for(const timer of timers)rawTimeout(()=>{},0);timers.clear();window.__synthetic.active=0;},
      speak:(utterance)=>{
        const mine=++generation;window.__synthetic.speakCalls++;window.__synthetic.starts++;window.__synthetic.active++;window.__synthetic.maxActive=Math.max(window.__synthetic.maxActive,window.__synthetic.active);
        if(typeof utterance.onstart==='function')utterance.onstart();
        const attempt=()=>{
          if(mine!==generation)return;
          const current=(document.getElementById('current-step')||{}).textContent||'';
          const match=current.match(/第\\s*(\\d+)\\s*段/);const number=match?Number(match[1]):0;
          if(window.__testHoldStep===number&&!window.__testRelease){const id=rawTimeout(attempt,8);timers.add(id);return;}
          const id=rawTimeout(()=>{timers.delete(id);if(mine!==generation)return;window.__synthetic.active=Math.max(0,window.__synthetic.active-1);window.__synthetic.ends++;if(typeof utterance.onend==='function')utterance.onend();},window.__testEventDelay);timers.add(id);
        };
        attempt();
      }
    };
    Object.defineProperty(window,'speechSynthesis',{configurable:true,value:shim});
  })();`;
}
function fileUrl(relative) { return pathToFileURL(path.resolve(root, relative)).href; }
async function currentScene(page) {
  return page.locator('#current-step').textContent();
}
function sceneNumber(text) { const m=(text||'').match(/第\s*(\d+)\s*段/);return m?Number(m[1]):0; }
async function manualProbe(page,key){
  return page.evaluate((kind)=>{
    const text=document.querySelector('#practice-visual svg')?.textContent||'';
    if(kind==='primary-lower-input-process-output')return {inputB:text.includes('按键 B')};
    if(kind==='primary-lower-sorting-by-rule')return {colorRule:text.includes('按颜色')};
    if(kind==='primary-lower-robot-instructions')return {blocked:text.includes('障碍')};
    if(kind==='primary-upper-pixels-build-picture')return {size:text.includes('8×8')};
    if(kind==='primary-upper-cards-bubble-sort')return {values:document.querySelector('#sort-input').value};
    if(kind==='primary-upper-message-packets')return {order:text.includes('2、3、1')};
    if(kind==='junior-linear-search')return {target:document.querySelector('#search-target').value};
    if(kind==='junior-stack-and-queue')return {queueOrder:text.includes('A、B')};
    if(kind==='junior-training-and-testing')return {test3:text.includes('T3')};
    if(kind==='senior-shortest-path')return {start:document.querySelector('#path-start').value,end:document.querySelector('#path-end').value};
    if(kind==='senior-gradient-descent')return {alpha:document.querySelector('#alpha').value};
    if(kind==='senior-classification-metrics')return {threshold:document.querySelector('#threshold').value};
    return {};
  },key);
}
async function manualExperiment(page,key) {
  await page.locator('#practice-toggle').click();
  await page.locator('#practice-panel').waitFor({state:'visible',timeout:2500});
  if(key==='primary-lower-input-process-output'){
    await page.locator('[data-action="inputB"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('三角灯亮'), '按键 B 手动实验产生三角灯输出', key);
  } else if(key==='primary-lower-sorting-by-rule'){
    await page.locator('[data-rule="color"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('按照颜色'), '手动切换颜色分类规则', key);
  } else if(key==='primary-lower-robot-instructions'){
    await page.locator('[data-route="wrong"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('障碍'), '错误路线手动检查会停止在障碍前', key);
  } else if(key==='primary-upper-pixels-build-picture'){
    await page.locator('[data-size="8"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('8×8'), '像素练习能切换到 8×8 网格', key);
  } else if(key==='primary-upper-cards-bubble-sort'){
    await page.locator('#sort-input').fill('3,2,2,1');await page.locator('[data-action="sort"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('[1, 2, 2, 3]'), '冒泡排序练习保留重复数字并正确排序', key);
    await page.locator('#sort-input').fill('3,2,');await page.locator('[data-action="sort"]').click();
    verify((await page.locator('#practice-error').textContent()).includes('请输入'), '非法排序输入明确拒绝且保留上一有效结果', key);
    await page.locator('#sort-input').fill('3,2,2,1');
  } else if(key==='primary-upper-message-packets'){
    await page.locator('[data-order="2,3,1"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('明天图书馆见'), '消息块按编号重组完整短消息', key);
  } else if(key==='junior-linear-search'){
    await page.locator('#search-target').fill('8');await page.locator('[data-action="search"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('没有找到 8'), '线性查找练习能报告未命中', key);
  } else if(key==='junior-stack-and-queue'){
    await page.locator('[data-kind="queue"]').click();
    await page.locator('[data-action="push"]').click();await page.locator('[data-action="push"]').click();await page.locator('[data-action="push"]').click();
    await page.locator('[data-action="pop"]').click();await page.locator('[data-action="pop"]').click();
    verify((await page.locator('#practice-visual').textContent()).includes('离开顺序：A、B'), '队列手动出队从队首移除 A、B', key);
  } else if(key==='junior-training-and-testing'){
    await page.locator('[data-test="2"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('本次不同'), '最近邻练习重新计算并揭示 T3 判断不同', key);
  } else if(key==='senior-shortest-path'){
    await page.locator('#path-start').selectOption('F');await page.locator('#path-end').selectOption('E');await page.locator('[data-action="path"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('无法到达'), 'Dijkstra 实践能报告不可达终点', key);
  } else if(key==='senior-gradient-descent'){
    await page.locator('#alpha').selectOption('1.1');await page.locator('[data-action="gradient"]').click();
    verify((await page.locator('#practice-output').textContent()).includes('步长 1.1'), '梯度下降练习按所选步长重算', key);
  } else if(key==='senior-classification-metrics'){
    await page.locator('#threshold').fill('0.65');await page.locator('[data-action="metrics"]').click();
    const output=await page.locator('#practice-output').textContent();
    verify(output.includes('66.7%')&&output.includes('50%'), '阈值练习动态计算精确率约 66.7% 和召回率 50%', key);
  }
  const before=JSON.stringify(await manualProbe(page,key));
  await page.evaluate(()=>{window.__testHoldStep=1;window.__testRelease=false;});
  await page.locator('#restart').click();
  await page.waitForFunction(()=>/第\s*1\s*段/.test(document.querySelector('#current-step').textContent),null,{timeout:2500});
  await page.locator('#practice-toggle').click();
  await page.locator('#practice-panel').waitFor({state:'visible',timeout:2000});
  const after=JSON.stringify(await manualProbe(page,key));
  verify(before===after, '从头播放后手动实践参数状态保留', key);
  await page.evaluate(()=>{window.__testRelease=true;window.__testHoldStep=null;});
}

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
  for(const item of catalog){
    const key=item.id;const page=await browser.newPage({viewport:{width:1366,height:768}});const consoleErrors=[];const pageErrors=[];
    console.log('[browser] start '+key);
    page.on('pageerror',e=>pageErrors.push(String(e)));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
    const sample={id:key,views:[],synthetic_tts:{starts:0,ends:0},screenshots:[]};
    try{
      await page.addInitScript({content:syntheticSpeechScript({voices:true})});
      await page.goto(fileUrl(item.standalone_html));
      verify((await page.title()).includes(item.title),'页面标题与课件目录一致',key);
      verify(await page.locator('#begin').isVisible(),'初始状态显示开始播放按钮',key);
      verify((await page.locator('#play-status').textContent()).includes('尚未开始'),'未点击前保持静音待机',key);
      verify(await page.locator('#begin').count()===1,'独立页面只有一个开始播放入口',key);
      verify(await page.evaluate(()=>window.__synthetic.starts===0),'开始前没有触发朗读事件',key);
      for(const [width,height] of sizes){
        await page.setViewportSize({width,height});await page.waitForTimeout(25);
        const view=await page.evaluate(()=>{
          const start=document.querySelector('#begin').getBoundingClientRect();
          const svg=document.querySelector('.lesson-svg').getBoundingClientRect();
          return {width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,start:{x:start.x,y:start.y,w:start.width,h:start.height},svg:{x:svg.x,y:svg.y,w:svg.width,h:svg.height}};
        });
        const noOverflow=view.scrollWidth<=width;
        const buttonVisible=view.start.w>=44&&view.start.h>=44&&view.start.x>=0&&view.start.y>=0&&view.start.x+view.start.w<=width&&view.start.y+view.start.h<=height;
        verify(noOverflow,`${width}x${height} 页面无横向溢出`,key);
        verify(buttonVisible,`${width}x${height} 初始开始按钮完整可见`,key);
        sample.views.push({...view,start_visible:buttonVisible,horizontal_overflow:!noOverflow});
      }
      console.log('[browser] viewport checks '+key);
      await page.setViewportSize({width:1366,height:768});
      const keySteps=targets[key]||[item.stage==='SENIOR'?1:1];
      await page.evaluate((n)=>{window.__testHoldStep=n;window.__testRelease=false;},1);
      await page.locator('#begin').click();
      await page.waitForFunction(()=>document.querySelector('#play-status').textContent==='正在朗读本段',null,{timeout:3000});
      sample.screenshots.push('screenshots/'+key+'-desktop-running.png');
      await page.screenshot({path:path.join(shotDir,key+'-desktop-running.png')});
      if(item.stage==='PRIMARY_LOWER'){
        await page.setViewportSize({width:320,height:568});await page.waitForTimeout(35);
        sample.screenshots.push('screenshots/'+key+'-320x568.png');
        await page.screenshot({path:path.join(shotDir,key+'-320x568.png')});
        await page.setViewportSize({width:1366,height:768});
      }
      const activeViews=[];
      for(const [width,height] of sizes){
        await page.setViewportSize({width,height});await page.waitForTimeout(20);
        const active=await page.evaluate(()=>({
          scrollWidth:document.documentElement.scrollWidth,
          controls:[...document.querySelectorAll('#player-controls button')].map(b=>{const r=b.getBoundingClientRect();return {w:r.width,h:r.height,x:r.x,y:r.y,right:r.right,bottom:r.bottom,display:getComputedStyle(b).display};})
        }));
        const controlsVisible=active.controls.length===4&&active.controls.every(r=>r.w>=44&&r.h>=44&&r.x>=0&&r.right<=width&&r.y>=0&&r.bottom<=height&&r.display!=='none');
        verify(active.scrollWidth<=width,`${width}x${height} 播放中无横向溢出`,key);
        verify(controlsVisible,`${width}x${height} 播放控制完整可见且触控区足够`,key);
        activeViews.push({width,height,controls_visible:controlsVisible,horizontal_overflow:active.scrollWidth>width});
      }
      sample.active_control_views=activeViews;
      await page.setViewportSize({width:1366,height:768});
      // The first utterance is held to verify pause and current-scene replay before an end event.
      await page.evaluate(()=>{window.__testRelease=true;});
      await page.waitForFunction(()=>/第\s*2\s*段/.test(document.querySelector('#current-step').textContent),null,{timeout:3000});
      await page.locator('#pause').click();
      verify((await page.locator('#play-status').textContent()).includes('已暂停'),'暂停后状态提示当前段将重播',key);
      const pausedAt=sceneNumber(await currentScene(page));await page.waitForTimeout(250);
      verify(sceneNumber(await currentScene(page))===pausedAt,'暂停期间场景没有继续推进',key);
      await page.locator('#pause').click();
      await page.waitForFunction(()=>/第\s*3\s*段/.test(document.querySelector('#current-step').textContent),null,{timeout:3000});
      await page.evaluate(()=>{window.__testHoldStep=3;window.__testRelease=false;});
      await page.locator('#replay').click();
      await page.waitForFunction(()=>/第\s*3\s*段/.test(document.querySelector('#current-step').textContent)&&document.querySelector('#play-status').textContent==='正在朗读本段',null,{timeout:3000});
      verify(sceneNumber(await currentScene(page))===3,'重播本段重新显示并朗读当前段',key);
      await page.evaluate(()=>{window.__testRelease=true;});
      await page.waitForFunction(()=>/第\s*4\s*段/.test(document.querySelector('#current-step').textContent),null,{timeout:3000});
      await page.evaluate(()=>{
        window.__testHoldStep=4;window.__testRelease=false;
        Object.defineProperty(document,'hidden',{configurable:true,value:true});
        document.dispatchEvent(new Event('visibilitychange'));
      });
      verify((await page.locator('#play-status').textContent()).includes('已暂停'),'标签页隐藏时暂停内部推进',key);
      await page.waitForTimeout(220);
      verify(sceneNumber(await currentScene(page))===4,'标签页隐藏期间保持当前场景',key);
      await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});});
      await page.locator('#pause').click();
      await page.waitForFunction(()=>/第\s*4\s*段/.test(document.querySelector('#current-step').textContent)&&document.querySelector('#play-status').textContent==='正在朗读本段',null,{timeout:3000});
      verify(sceneNumber(await currentScene(page))===4,'重新显示并继续后从当前段开头重读',key);
      await page.evaluate(()=>{window.__testRelease=true;window.__testHoldStep=null;});
      await page.waitForFunction(()=>/第\s*5\s*段/.test(document.querySelector('#current-step').textContent),null,{timeout:3000});
      await page.evaluate(()=>{window.__testHoldStep=1;window.__testRelease=false;});
      await page.locator('#restart').click();
      await page.waitForFunction(()=>/第\s*1\s*段/.test(document.querySelector('#current-step').textContent)&&document.querySelector('#play-status').textContent==='正在朗读本段',null,{timeout:3000});
      verify(sceneNumber(await currentScene(page))===1,'从头播放返回第一段',key);
      await page.locator('#restart').click();await page.locator('#restart').click();
      verify(await page.evaluate(()=>window.__synthetic.maxActive<=1),'快速重复从头播放不会并发朗读',key);
      await page.evaluate((n)=>{window.__testHoldStep=n;window.__testRelease=false;},keySteps[0]);
      await page.evaluate(()=>{window.__testRelease=true;});
      for(let i=0;i<keySteps.length;i++){
        const step=keySteps[i];
        await page.evaluate((n)=>{window.__testHoldStep=n;window.__testRelease=false;},step);
        await page.waitForFunction((n)=>new RegExp('第\\s*'+n+'\\s*段').test(document.querySelector('#current-step').textContent),step,{timeout:5000});
        await page.waitForTimeout(15);
        const shot=key+'-key-step-'+String(step).padStart(2,'0')+'.png';
        sample.screenshots.push('screenshots/'+shot);
        await page.screenshot({path:path.join(shotDir,shot)});
        verify(sceneNumber(await currentScene(page))===step,`关键截图对应第 ${step} 段`,key);
        await page.evaluate(()=>{window.__testRelease=true;window.__testHoldStep=null;});
        if(i+1<keySteps.length){
          await page.evaluate((n)=>{window.__testHoldStep=n;window.__testRelease=false;},keySteps[i+1]);
        }
      }
      await page.locator('#finished').waitFor({state:'visible',timeout:8000});
      console.log('[browser] playback finished '+key);
      verify((await page.locator('#play-status').textContent())==='播放完了','连续播放到结尾并保留最后画面',key);
      const last=await currentScene(page);await page.waitForTimeout(80);
      verify((await currentScene(page))===last,'播放结束后没有自动循环',key);
      await manualExperiment(page,key);
      console.log('[browser] manual practice checked '+key);
      sample.synthetic_tts=await page.evaluate(()=>({...window.__synthetic}));
      sample.console_errors=consoleErrors;sample.page_errors=pageErrors;
      verify(consoleErrors.length===0&&pageErrors.length===0,'浏览器控制台没有相关运行错误',key);
      entries.push(sample);
    }catch(error){
      console.error('[browser] failure '+key+': '+String(error&&error.message||error));
      failures.push({sample:key,message:'浏览器流程异常：'+String(error&&error.stack||error)});
      entries.push({...sample,console_errors:consoleErrors,page_errors:pageErrors});
    }finally{await page.close();}
  }

  // No-voice fallback: accelerated reading clocks are test-only so all 127 scenes can be exercised quickly.
  for(const item of catalog){
    const page=await browser.newPage({viewport:{width:390,height:844}});
    console.log('[browser] silent '+item.id);
    try{
      await page.addInitScript({content:syntheticSpeechScript({voices:false,accelerateSilent:true})});
      await page.goto(fileUrl(item.standalone_html));
      await page.locator('#begin').click();
      await page.locator('#finished').waitFor({state:'visible',timeout:7000});
      const state=await page.evaluate(()=>({status:document.querySelector('#play-status').textContent,events:window.__synthetic,step:document.querySelector('#current-step').textContent}));
      verify(state.status==='播放完了','无普通话声音时按字幕路径自动播完（测试计时加速）',item.id);
      verify(state.events.speakCalls===0&&state.events.starts===0,'无声路径不伪称朗读或发出 TTS',item.id);
    }catch(error){failures.push({sample:item.id,message:'无声路径异常：'+String(error&&error.stack||error)});}finally{await page.close();}
  }

  // Muted playback uses the same silent reader even when Mandarin TTS is available.
  {
    const item=catalog[0],page=await browser.newPage({viewport:{width:390,height:844}});
    console.log('[browser] muted path');
    try{
      await page.addInitScript({content:syntheticSpeechScript({voices:true,accelerateSilent:true})});await page.goto(fileUrl(item.standalone_html));
      await page.locator('.advanced summary').click();await page.locator('#mute').check();await page.locator('#begin').click();
      await page.locator('#finished').waitFor({state:'visible',timeout:5000});
      const events=await page.evaluate(()=>window.__synthetic);verify(events.speakCalls===0,'静音设置不启动 TTS，字幕路径仍播放到结尾',item.id);
    }catch(error){failures.push({sample:item.id,message:'静音路径异常：'+String(error&&error.stack||error)});}finally{await page.close();}
  }
  // Pausing a no-voice read cancels its reading clock; continue restarts the same caption.
  {
    const item=catalog[0],page=await browser.newPage({viewport:{width:390,height:844}});
    try{
      await page.addInitScript({content:syntheticSpeechScript({voices:false,accelerateSilent:false})});await page.goto(fileUrl(item.standalone_html));
      await page.locator('#begin').click();await page.waitForFunction(()=>document.querySelector('#play-status').textContent.includes('没有普通话声音'),null,{timeout:3000});
      const at=sceneNumber(await currentScene(page));await page.locator('#pause').click();await page.waitForTimeout(120);
      verify(sceneNumber(await currentScene(page))===at,'无声字幕阅读暂停时计时不推进',item.id);
      await page.evaluate(()=>{window.__testAccelerateSilent=true;});await page.locator('#pause').click();
      await page.locator('#finished').waitFor({state:'visible',timeout:5000});
      verify((await currentScene(page)).includes('第 8 段'),'无声路径继续后从当前段完成播放',item.id);
    }catch(error){failures.push({sample:item.id,message:'无声暂停/继续路径异常：'+String(error&&error.stack||error)});}finally{await page.close();}
  }

  // Synthetic K12 host bridge contract smoke test; this is not a live platform import.
  {
    const item=catalog[0],page=await browser.newPage({viewport:{width:1366,height:768}});
    console.log('[browser] synthetic host bridge');
    try{
      await page.addInitScript({content:`(() => {
        window.__hostCalls=[];window.__speechCalls=0;
        const sdk={ready:async()=>{const d=window.LESSON_DEFINITION;return{currentScene:'scene-01',gameState:{},scenes:d.steps.map((s,i)=>({id:'scene-'+String(i+1).padStart(2,'0'),title:s.title,summary:s.text})),prompts:d.steps.map((s,i)=>({id:'scene-'+String(i+1).padStart(2,'0')+'-read',scene_id:'scene-'+String(i+1).padStart(2,'0'),text:s.text,trigger:'SCENE_ENTER'}))};},
          scene:{enter:async id=>{window.__hostCalls.push(['scene.enter',id]);}},
          narration:{onState:()=>()=>{}},
          workspace:{register:async(commands,handler,options)=>{window.__hostCalls.push(['register',commands,options.playback_steps]);window.__hostHandler=handler;return{embedded:true};}},
          assets:{url:()=>''}
        };
        window.K12=sdk;
      })();`});
      await page.addInitScript({content:syntheticSpeechScript({voices:true})});await page.goto(fileUrl(item.standalone_html));
      await page.waitForFunction(()=>document.body.classList.contains('embedded')&&typeof window.__hostHandler==='function',null,{timeout:3000});
      verify(await page.locator('#begin').isHidden(),'宿主确认 embedded 后隐藏内部开始控件',item.id);
      await page.evaluate(()=>window.__hostHandler({command:'scene',scene_id:'scene-02'}));
      verify((await currentScene(page)).includes('第 2 段'),'宿主 scene 命令切换实际画面',item.id);
      verify((await page.evaluate(()=>window.__hostCalls.some(x=>x[0]==='scene.enter'&&x[1]==='scene-02'))),'scene 命令等待 SDK 场景确认',item.id);
      await page.evaluate(()=>window.__hostHandler({command:'demonstrate',prompt_id:'scene-02-read'}));
      verify((await page.locator('#caption').textContent()).length>0,'demonstrate 对应提示显示字幕与画面',item.id);
      verify(await page.evaluate(()=>window.__synthetic.speakCalls===0),'宿主接管后 HTML 不启动第二套 TTS',item.id);
      await page.evaluate(()=>window.__hostHandler({command:'demonstrate',prompt_id:null}));
      verify(await page.locator('#practice-panel').isVisible(),'demonstrate null 显示手动实践控件',item.id);
      await page.locator('[data-action="inputB"]').click();
      await page.evaluate(()=>window.__hostHandler({command:'scene',scene_id:'scene-03'}));
      await page.evaluate(()=>window.__hostHandler({command:'demonstrate',prompt_id:'scene-03-read'}));
      await page.evaluate(()=>window.__hostHandler({command:'demonstrate',prompt_id:null}));
      verify((await page.locator('#practice-visual svg').textContent()).includes('按键 B'),'宿主演示往返保留手动实践状态',item.id);
      await page.evaluate(()=>window.__hostHandler({command:'pause'}));
      verify(await page.evaluate(()=>window.__synthetic.speakCalls===0),'宿主 pause 不产生内部朗读',item.id);
    }catch(error){failures.push({sample:item.id,message:'K12 桥接模拟异常：'+String(error&&error.stack||error)});}finally{await page.close();}
  }
  await browser.close();
  const result={status:failures.length?'failed':'passed',date:new Date().toISOString(),browser:'Google Chrome 154.0.8037.57 headless',sample_count:catalog.length,viewport_sizes:sizes.map(x=>x.join('x')),checks:checkCount,synthetic_tts:true,real_browser_tts:'not audibly verified',real_media:'none in package',silent_path:'all samples exercised with accelerated reading timers; one real browser no-voice observation in CUA',platform:'project package parser passed; synthetic K12 bridge mock passed; actual platform import not verified',screenshots:entries.flatMap(x=>x.screenshots||[]),samples:entries,failures};
  fs.writeFileSync(path.join(root,'test-results','browser-validation.json'),JSON.stringify(result,null,2)+'\n');
  const md=['# 浏览器检查记录','',`状态：${result.status}；${checkCount} 项检查；Chrome 154.0.8037.57。`,`视口：${sizes.map(x=>x.join('×')).join('、')}。`,'','12 个样例均在真实浏览器中检查页面标题、初始静音状态、单一开始入口、四种视口横向溢出和按钮可见性、合成 TTS start/end 同步、暂停、继续、重播、从头播放、结尾不循环和手动实践。','',`TTS 证据：${result.real_browser_tts}。检查事件由合成 SpeechSynthesisUtterance 测试对象驱动，不代表真实发声。`,'无声和静音路径逐样例连续播放至结尾；为缩短自动检查时间，测试环境加速了字幕阅读计时。CUA 实际浏览器观察到“没有普通话声音，按字幕阅读时间自动继续”。','',`平台接入：${result.platform}。`,''];
  if(failures.length)md.push('## 失败项','',...failures.map(x=>'- '+x.sample+': '+x.message));
  fs.writeFileSync(path.join(root,'test-results','browser-validation.md'),md.join('\n'));
  console.log(`browser validation: ${result.status}; ${checkCount} checks; ${result.screenshots.length} screenshots; ${failures.length} failures`);
  for(const failure of failures)console.error(failure.sample+': '+failure.message);
  if(failures.length)process.exitCode=1;
})();
