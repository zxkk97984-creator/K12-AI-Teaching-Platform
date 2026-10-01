createLearningActivity({
  scenes: window.LESSON_SCENES,
  restore: raw => ({ bits: Array.from({length:5}, (_, i) => Array.isArray(raw.bits) && raw.bits[i] === true), target: Number.isInteger(raw.target) && raw.target >= 0 && raw.target <= 31 ? raw.target : 13 }),
  reset: state => { state.bits = Array(5).fill(false); },
  render: function renderCards(node, state, scene, save) {
    const weights = [16,8,4,2,1];
    const total = weights.reduce((sum, value, index) => sum + (state.bits[index] ? value : 0), 0);
    node.innerHTML = `<div class="cards">${weights.map((value,index) => `<button class="bit" data-bit="${index}" aria-pressed="${state.bits[index]}" aria-label="${value}卡片，${state.bits[index] ? '开' : '关'}">${state.bits[index] ? value : '0'}<small>权重 ${value}</small></button>`).join('')}</div><p class="result">${state.bits.map(bit=>bit?'1':'0').join('')}₂ = ${total}₁₀</p><p class="summary">开启卡片相加：${weights.filter((_,i)=>state.bits[i]).join(' + ') || '0'} = ${total}</p><div class="controls"><label>目标数字 <input id="target" type="number" min="0" max="31" value="${state.target}"></label><button id="clear">关闭所有卡片</button></div><p class="summary">目标 ${state.target}：${total === state.target ? '你已经表示出这个数字！' : '试着调整卡片，让总和等于目标。'}</p>`;
    node.querySelectorAll('[data-bit]').forEach(button => { button.onclick = () => { const index=Number(button.dataset.bit); state.bits[index]=!state.bits[index]; renderCards(node,state,scene,save); void save(); }; });
    node.querySelector('#target').onchange = event => { const value=Number(event.target.value); if(Number.isInteger(value)&&value>=0&&value<=31){state.target=value;renderCards(node,state,scene,save);void save();}else event.target.value=String(state.target); };
    node.querySelector('#clear').onclick = async () => { if (state.bits.some(Boolean) && !await confirmLearningReset('关闭所有卡片会清除当前组合，确定继续吗？')) return; state.bits=weights.map(()=>false); renderCards(node,state,scene,save); void save(); };
  },
}).catch(error => { document.getElementById('activity-error').textContent=error.message; });
