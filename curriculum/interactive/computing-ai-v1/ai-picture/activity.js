const fruit = (kind) => kind === 'banana' ? '<svg viewBox="0 0 120 90" aria-label="黄色香蕉"><path d="M22 20c6 50 48 65 80 14-19 27-49 24-62-3Z" fill="#f1ca4f" stroke="#bf9633" stroke-width="3"/></svg>' : `<svg viewBox="0 0 120 90" aria-label="${kind === 'green' ? '绿色' : '红色'}苹果"><path d="M61 26c-24-21-49-3-36 31 14 31 24 21 35 20 14 4 25 8 37-21 12-34-14-50-36-30Z" fill="${kind === 'green' ? '#7fbd77' : '#df7869'}"/><path d="M60 26v-14m0 9c14-14 26-12 25-12-3 16-17 13-25 12Z" fill="#52815a" stroke="#52815a" stroke-width="3"/></svg>`;
createLearningActivity({
  scenes: window.LESSON_SCENES,
  restore: raw => ({ red: Boolean(raw.red), banana: Boolean(raw.banana), green: Boolean(raw.green) }),
  reset: state => { state.red = state.banana = state.green = false; },
  render: function renderPicture(node, state, scene, save) {
    node.innerHTML = `<p class="notice">样例推断规则 · 教学模拟，展示数据如何影响规则。</p><div class="training"><button data-kind="red" aria-pressed="${state.red}">${fruit('red')}<span>红苹果 · 苹果</span><p class="tag">${state.red ? '已加入样例' : '点击加入样例'}</p></button><button data-kind="banana" aria-pressed="${state.banana}">${fruit('banana')}<span>黄香蕉 · 香蕉</span><p class="tag">${state.banana ? '已加入样例' : '点击加入样例'}</p></button><button data-kind="green" aria-pressed="${state.green}">${fruit('green')}<span>绿苹果 · 苹果</span><p class="tag">${state.green ? '已加入样例' : '点击加入样例'}</p></button></div><p class="result" id="prediction"></p><p class="summary" id="rule"></p>`;
    const prediction = node.querySelector('#prediction');
    const rule = node.querySelector('#rule');
    if (!state.red || !state.banana) { prediction.textContent = '先加入红苹果和黄香蕉'; rule.textContent = '至少观察两类样例，再尝试给新图片分类。'; }
    else if (!state.green) { prediction.textContent = '绿色苹果 → 暂时认不出'; rule.textContent = '当前样例只支持颜色规则：红色是苹果，黄色是香蕉。它遇到绿色苹果就会失败。'; }
    else { prediction.textContent = '绿色苹果 → 苹果'; rule.textContent = '加入不同颜色的苹果后，模拟器改用形状规则：圆圆的是苹果，弯弯的是香蕉。真实模型也需要有代表性的数据。'; }
    node.querySelectorAll('[data-kind]').forEach(button => {
      button.onclick = () => { state[button.dataset.kind] = !state[button.dataset.kind]; thisRender(); void save(); };
    });
    const thisRender = () => { renderPicture(node, state, scene, save); };
  },
}).catch(error => { document.getElementById('activity-error').textContent = error.message; });
