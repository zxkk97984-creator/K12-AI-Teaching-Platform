function loopSnapshot(state) {
  const total = Array.from({length: state.step}, (_, index) => index + 1).filter(number => number % 2 === 0).reduce((sum, number) => sum + number, 0);
  const even = state.step > 0 && state.step % 2 === 0;
  const before = total - (even ? state.step : 0);
  const hint = state.step === 0 ? '先执行下一轮：检查第一个数字是否满足偶数条件。' : even ? `${state.step} 是偶数，条件成立，因此加入总和：total 从 ${before} 变为 ${total}。` : `${state.step} 是奇数，条件不成立，跳过累加：total 保持 ${total}。`;
  return {total, even, before, hint};
}
createLearningActivity({
  scenes: window.LESSON_SCENES,
  restore: raw => { const n=Number.isInteger(raw.n)&&raw.n>=1&&raw.n<=20?raw.n:8; return {n,step:Number.isInteger(raw.step)?Math.max(0,Math.min(n,raw.step)):0}; },
  reset: state => { state.step = 0; },
  hint: state => loopSnapshot(state).hint,
  render: function renderLoop(node, state, scene, save) {
    const {total, even, before, hint} = loopSnapshot(state);
    const line = state.step === 0 ? 0 : even ? 3 : 2;
    const code = ['total = 0', 'for number in range(1, n + 1):', '    if number % 2 == 0:', '        total += number'];
    node.innerHTML = `<div class="loop-workspace"><section class="loop-code" aria-label="程序与执行路径"><p class="section-label">看这里 · 本轮执行路径</p><pre class="code">${code.map((text, index) => `<span class="code-line ${index === line ? 'executing' : ''}" ${index === line ? 'aria-current="step"' : ''}><span class="line-number" aria-hidden="true">${index + 1}</span><code>${text}</code>${index === line ? '<span class="line-marker" aria-label="当前执行行">←</span>' : ''}</span>`).join('')}</pre><p class="condition-result">${state.step === 0 ? '还没有进入循环' : `条件 number % 2 == 0：${even ? '成立 ✓' : '不成立 · 跳过累加'}`}</p></section><section class="loop-data" aria-label="变量与数字序列"><p class="section-label">观察变化 · 变量</p><div class="variable-pair"><div><span>当前 number</span><strong>${state.step || '—'}</strong></div><div><span>累计 total</span><strong>${state.step ? `${before} → ${total}` : '0'}</strong></div></div><p class="result sr-only" tabindex="-1">当前 number = ${state.step || '—'} · total = ${total}</p><div class="chips" aria-label="数字执行序列">${Array.from({length: state.n}, (_, index) => index + 1).map(number => `<span class="chip ${number === state.step ? 'active' : ''} ${number > state.step ? 'eliminated' : ''}">${number}${number <= state.step && number % 2 === 0 ? ' ✓' : ''}</span>`).join('')}</div><p class="experiment-progress">实验进度：已检查 ${state.step} / ${state.n} 个数字${state.step === state.n ? ' · 循环已结束' : ''}</p></section></div><div class="controls loop-controls"><label>上限 n（1—20）<input id="n" type="number" min="1" max="20" value="${state.n}"></label><button id="step" class="primary" ${state.step >= state.n ? 'disabled' : ''}>执行下一轮</button></div><p class="summary operation-hint" role="status">${hint}</p><p class="notice">固定程序规则演示；真实代码执行请使用编程入门。实验结束后仍可继续学习其他环节。</p>`;
    node.querySelector('#step').onclick = () => { state.step=Math.min(state.n,state.step+1); renderLoop(node,state,scene,save); node.querySelector(state.step >= state.n ? '.result' : '#step').focus(); void save(); };
    node.querySelector('#n').onchange = async event => {
      const n=Number(event.target.value);
      if (Number.isInteger(n)&&n>=1&&n<=20) {
        if (state.step > 0 && !await confirmLearningReset('调整上限会清除当前实验的执行进度，课程环节会保留。')) { event.target.value=String(state.n); return; }
        state.n=n; state.step=0; renderLoop(node,state,scene,save); node.querySelector('#n').focus(); void save();
      } else event.target.value=String(state.n);
    };
  },
}).catch(error => { document.getElementById('activity-error').textContent=error.message; });
