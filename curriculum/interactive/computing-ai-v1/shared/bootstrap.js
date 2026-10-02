// Native confirm is unavailable in an allow-scripts-only sandbox.
window.confirmLearningReset = function (text) {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog'); dialog.className = 'learning-confirm';
    const message = document.createElement('p'); message.textContent = text;
    const controls = document.createElement('div'); controls.className = 'controls';
    const cancel = document.createElement('button'); cancel.textContent = '保留当前进度';
    const confirm = document.createElement('button'); confirm.textContent = '确认重置'; confirm.className = 'primary';
    const previous = document.activeElement;
    const finish = value => { dialog.close(); dialog.remove(); previous?.focus(); resolve(value); };
    cancel.onclick = () => finish(false); confirm.onclick = () => finish(true);
    dialog.oncancel = event => { event.preventDefault(); finish(false); };
    controls.append(cancel, confirm); dialog.append(message, controls); document.body.append(dialog); dialog.showModal(); cancel.focus();
  });
};
window.createLearningActivity = async function (lesson) {
  const status = document.getElementById('save-status');
  if (!window.K12) { status.textContent = '请在霜铃平台中打开此讲解。'; return; }
  const context = await K12.ready();
  const state = lesson.restore(context.gameState || {});
  let demonstration = null;
  let scene = Math.max(0, lesson.scenes.findIndex(item => item.id === context.currentScene));
  let saving = 0;
  let embedded = false;
  const caption = document.getElementById('caption');
  const error = document.getElementById('activity-error');
  const canvas = document.getElementById('visual');
  const report = () => {
    if (!K12.workspace || !embedded) return;
    const shown = demonstration || state;
    const hint = (lesson.hint?.(shown, scene) || canvas.querySelector('.summary')?.textContent || '动手操作，观察画面中的变化。').slice(0, 500);
    void K12.workspace.report({scene_id: lesson.scenes[scene].id, game_state: JSON.parse(JSON.stringify(shown)), hint}).catch(() => {});
  };
  const render = () => {
    document.getElementById('scene-title').textContent = lesson.scenes[scene].title;
    document.querySelectorAll('nav button').forEach((button, index) => button.setAttribute('aria-pressed', String(index === scene)));
    const prompt = (context.prompts || []).find(item => item.scene_id === lesson.scenes[scene].id && item.trigger === 'SCENE_ENTER');
    caption.textContent = prompt?.text || lesson.scenes[scene].text;
    lesson.render(canvas, demonstration || state, scene, save);
    // Demonstrations leave the student's saved experiment untouched.
    canvas.inert = Boolean(demonstration);
    document.body.classList.toggle('demonstrating', Boolean(demonstration));
    report();
  };
  async function save() {
    report();
    const generation = ++saving;
    status.textContent = '正在保存操作…'; error.textContent = '';
    try {
      const receipt = await K12.checkpoint.save(JSON.parse(JSON.stringify(state)));
      if (generation === saving) status.textContent = receipt.persisted === false ? '预览：未写入学习记录' : '操作已保存';
    } catch (caught) {
      if (generation === saving) { status.textContent = '操作未保存'; error.textContent = caught.message; document.getElementById('retry-save').hidden = false; }
    }
  }
  async function enter(id) {
    const index = lesson.scenes.findIndex(item => item.id === id);
    if (index < 0) throw new Error('环节不存在');
    await K12.scene.enter(id);
    if (scene !== index) { scene = index; render(); }
  }
  async function finish() {
    error.textContent = '';
    await save();
    if (error.textContent) throw new Error(error.textContent);
    await K12.complete({ visited_scene: lesson.scenes[scene].id });
  }
  const navigation = document.getElementById('scenes');
  lesson.scenes.forEach(item => {
    const button = document.createElement('button');
    button.textContent = `${lesson.scenes.indexOf(item) + 1}. ${item.title}`;
    button.onclick = () => enter(item.id).catch(caught => { error.textContent = caught.message; });
    navigation.appendChild(button);
  });
  K12.narration.onState(value => {
    document.body.classList.toggle('speaking', value.status === 'speaking');
    document.getElementById('voice-status').textContent = value.status === 'speaking' ? '霜铃正在朗读' : value.status === 'paused' ? '朗读已暂停' : value.status === 'unavailable' ? '没有可用中文声音，可阅读讲解' : value.status === 'error' ? '朗读失败，可重播或阅读讲解' : '霜铃预设讲解';
    if (value.subtitle) caption.textContent = value.subtitle;
  });
  document.getElementById('read').onclick = () => K12.narration.play(lesson.scenes[scene].id + '-read').catch(caught => { error.textContent = caught.message; });
  document.getElementById('ask').onclick = () => K12.askTeacher().catch(caught => { error.textContent = caught.message; });
  document.getElementById('retry-save').onclick = async () => { await save(); if (!error.textContent) document.getElementById('retry-save').hidden = true; };
  document.getElementById('finish').onclick = () => finish().catch(caught => { error.textContent = caught.message; });
  render();
  if (K12.workspace) {
    K12.workspace.onSession(value => {
      const index = lesson.scenes.findIndex(item => item.id === value.scene_id);
      if (index >= 0 && index !== scene) { scene = index; render(); }
    });
    const playbackSteps = lesson.demonstrations ? lesson.scenes.map(item => ({scene_id: item.id, prompt_id: item.id + '-read'})) : undefined;
    const commands = ['scene', 'pause', 'complete', ...(lesson.reset ? ['reset'] : []), ...(playbackSteps ? ['demonstrate'] : [])];
    try {
      const receipt = await K12.workspace.register(commands, async value => {
        if (value.command === 'scene') await enter(value.scene_id);
        else if (value.command === 'pause') lesson.pause?.();
        else if (value.command === 'demonstrate') {
          if (value.prompt_id === null) demonstration = null;
          else {
            const apply = lesson.demonstrations?.[value.prompt_id];
            if (!apply || !playbackSteps.some(step => step.prompt_id === value.prompt_id && step.scene_id === lesson.scenes[scene].id)) throw new Error('当前环节没有这个自动演示');
            demonstration = lesson.restore({});
            apply(demonstration);
          }
          render();
        }
        else if (value.command === 'reset' && lesson.reset) { lesson.reset(state); render(); await save(); if (error.textContent) throw new Error(error.textContent); }
        else if (value.command === 'complete') await finish();
      }, {playback_steps: playbackSteps});
      if (receipt.embedded === true) {
        const allowed = ['font-family', 'text', 'muted', 'surface', 'soft', 'line', 'accent', 'radius'];
        for (const key of allowed) if (typeof receipt.theme?.[key] === 'string') document.documentElement.style.setProperty('--lesson-' + key, receipt.theme[key]);
        embedded = true;
        document.body.classList.add('embedded');
        report();
      }
    } catch { /* An older host keeps all authored controls available. */ }
  }
};
