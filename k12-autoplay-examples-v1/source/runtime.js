(function () {
  'use strict';
  var lesson = window.LESSON_DEFINITION;
  var byId = function (id) { return document.getElementById(id); };
  var stageNode = byId('visual');
  var captionNode = byId('caption');
  var statusNode = byId('play-status');
  var currentNode = byId('current-step');
  var beginButton = byId('begin');
  var pauseButton = byId('pause');
  var replayButton = byId('replay');
  var restartButton = byId('restart');
  var practiceButton = byId('practice-toggle');
  var index = 0;
  var mode = 'ready';
  var generation = 0;
  var timer = null;
  var embedded = false;
  var hostReady = false;
  var hostContext = null;
  var practiceOpen = false;
  var lastState = null;
  var rateValue = 1;
  var voicesChangeHandler = null;
  var practice = initialPractice();
  practice.operated = false;
  var practiceRevision = 0;
  var restoreNotice = '';
  var saveNotice = document.createElement('p');
  saveNotice.id = 'practice-save-status';
  saveNotice.setAttribute('role', 'status');
  byId('practice-error').after(saveNotice);
  var reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function n(value) { return Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 3}); }
  function text(x, y, value, cls, anchor) {
    return '<text x="' + x + '" y="' + y + '" class="' + (cls || '') + '" text-anchor="' + (anchor || 'middle') + '">' + esc(value) + '</text>';
  }
  function line(x1,y1,x2,y2,cls,extra) {
    return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" class="' + (cls || '') + '" ' + (extra || '') + '/>';
  }
  function rect(x,y,w,h,rx,cls,extra) {
    return '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="' + (rx || 0) + '" class="' + (cls || '') + '" ' + (extra || '') + '/>';
  }
  function svg(inner, label, cls) {
    return '<svg class="lesson-svg ' + (cls || '') + '" viewBox="0 0 960 520" role="img" aria-label="' + esc(label) + '" xmlns="http://www.w3.org/2000/svg"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 8 4 0 8Z" fill="#61758a"/></marker><pattern id="wall" width="12" height="12" patternUnits="userSpaceOnUse"><path d="M0 0 12 12M12 0 0 12" stroke="#9b8875" stroke-width="2"/></pattern></defs>' + inner + '</svg>';
  }
  function animateMove(dx, dy) {
    if (reducedMotion || (!dx && !dy)) return '';
    return '<animateTransform attributeName="transform" type="translate" from="' + dx + ' ' + dy + '" to="0 0" dur="0.55s" additive="sum" fill="freeze"/>';
  }
  function tileShape(shape, color, cx, cy, size, label) {
    var shapeSvg = shape === 'circle'
      ? '<circle cx="' + cx + '" cy="' + cy + '" r="' + size/2 + '" fill="' + color + '" stroke="#24364b" stroke-width="3"/>'
      : shape === 'triangle'
        ? '<path d="M' + cx + ' ' + (cy-size/2) + ' L' + (cx+size/2) + ' ' + (cy+size/2) + ' L' + (cx-size/2) + ' ' + (cy+size/2) + ' Z" fill="' + color + '" stroke="#24364b" stroke-width="3"/>'
        : '<rect x="' + (cx-size/2) + '" y="' + (cy-size/2) + '" width="' + size + '" height="' + size + '" rx="5" fill="' + color + '" stroke="#24364b" stroke-width="3"/>';
    return shapeSvg + text(cx, cy+size/2+25, label, 'small-label');
  }
  function renderInput(state) {
    var zones = [
      {x:65,title:'收到信息',active:state.stage === 'input'},
      {x:365,title:'照规则处理',active:state.stage === 'process'},
      {x:665,title:'给出结果',active:state.stage === 'output'}
    ];
    var s = '';
    zones.forEach(function (z) {
      s += rect(z.x,105,230,270,24,z.active ? 'zone active' : 'zone');
      s += text(z.x+115,144,z.title,'zone-title');
    });
    s += rect(383,205,194,120,18,'device-body');
    s += text(480,245,'小设备','device-title');
    s += text(480,284,state.rule || '按键 A → 圆灯亮','rule-text');
    s += line(285,240,355,240,'flow-line','marker-end="url(#arrow)"');
    s += line(605,240,650,240,'flow-line','marker-end="url(#arrow)"');
    s += rect(95,185,170,110,16,'input-box');
    s += text(180,225,state.input || '按键 A','device-title');
    s += text(180,264,'指令','small-label');
    if (state.input) {
      var px = state.stage === 'input' ? 180 : state.stage === 'process' ? 340 : 630;
      var previousX = state.prev_stage === 'input' ? 180 : state.prev_stage === 'process' ? 340 : state.prev_stage === 'output' ? 630 : px;
      s += '<g class="travel-token"><circle cx="' + px + '" cy="240" r="24" class="packet"/>' + text(px,247,state.input === '按键 A' ? 'A' : 'B','token-letter') + animateMove(previousX-px,0) + '</g>';
    }
    s += '<g class="lamp ' + (state.output ? 'lit' : '') + '"><circle cx="780" cy="236" r="54" class="lamp-shell"/><path d="M748 292h64v22h-64z" class="lamp-base"/></g>';
    if (state.output === '圓燈亮' || state.output === '圆灯亮') s += '<circle cx="780" cy="236" r="34" class="output-light"/>';
    else if (state.output === '三角灯亮') s += '<path d="M780 202 812 259h-64z" class="output-light"/>';
    else if (state.output === '方灯亮') s += '<rect x="752" y="208" width="56" height="56" rx="5" class="output-light"/>';
    s += text(180,426,'输入：' + (state.input || '等待指令'),'small-label');
    s += text(480,426,'规则写在设备里','small-label');
    s += text(780,426,'输出：' + (state.output || '尚未显示'),'small-label');
    return svg(s,'输入移动到设备，处理规则突出显示，输出灯发生变化');
  }
  function renderSorting(state) {
    var colors = {red:'#d66b61',blue:'#6c8db2',yellow:'#d8ae4c',green:'#6f9b76'};
    var groups = state.groups || [];
    var s = text(480,45,state.rule === 'shape' ? '本轮规则：按形状' : '本轮规则：按颜色','section-title');
    var names = state.rule === 'shape' ? ['圆形','三角形','方形'] : ['红色','蓝色','黄色'];
    var cols = [160,480,800];
    if(state.stage==='pool'){
      s += rect(105,95,750,320,20,'zone');
      s += text(480,133,'待分类图形 · 先看特征，再按规则移动','zone-title');
      (state.items||[]).forEach(function(item,i){var xx=190+(i%3)*285,yy=220+Math.floor(i/3)*105;s+=tileShape(item.shape,colors[item.color],xx,yy,50,item.colorName+' '+item.shapeName);});
      s += text(480,470,'红圆形和蓝圆形：颜色不同，形状相同。','small-label');
      return svg(s,'等待分类的红蓝黄图形，展示颜色和形状两种特征');
    }
    names.forEach(function (name, k) {
      s += rect(cols[k]-128,82,256,345,20,'zone');
      s += text(cols[k],119,name,'zone-title');
      var group = groups[k] || [];
      group.forEach(function (item,j) {
        var yy = item.y == null ? 178 + j*92 : item.y;
        var xx = item.x == null ? cols[k] : item.x;
        var dx = item.from_x == null ? 0 : item.from_x - xx;
        var dy = item.from_y == null ? 0 : item.from_y - yy;
        s += '<g class="shape-item">' + tileShape(item.shape,colors[item.color],xx,yy,44,item.colorName + ' ' + item.shapeName) + animateMove(dx,dy) + '</g>';
      });
    });
    s += text(480,475,state.note || '同一物品会依照当前规则进入对应区域。','small-label');
    return svg(s,'图形按照当前规则进入圆形、三角形、方形或颜色区域');
  }
  function renderRobot(state) {
    var x0=110,y0=115,cell=72,s='',goal=state.goal||lesson.data.goal;
    s += text(458,42,'按地图坐标行走：每个箭头只走一格','section-title');
    for(var r=0;r<5;r++) for(var c=0;c<5;c++) {
      var xx=x0+c*cell, yy=y0+r*cell, key=r+','+c;
      s += rect(xx,yy,cell,cell,5,'grid-cell');
      if(r===0&&c===0){s+=text(xx+36,yy+43,'起点','map-label');}
      if(r===goal[0]&&c===goal[1]){s+=text(xx+36,yy+43,'终点','map-label');}
      if((state.walls||[]).some(function(w){return w[0]===r&&w[1]===c;})) s+=rect(xx+5,yy+5,cell-10,cell-10,4,'wall-cell','fill="url(#wall)"')+text(xx+36,yy+44,'障碍','map-label');
      if((state.path||[]).some(function(p){return p[0]===r&&p[1]===c;})) s+='<circle cx="'+(xx+36)+'" cy="'+(yy+36)+'" r="8" class="trail-dot"/>';
    }
    var p=state.position||[0,0], prev=state.previous||p, dx=(prev[1]-p[1])*cell,dy=(prev[0]-p[0])*cell;
    var rx=x0+p[1]*cell+36, ry=y0+p[0]*cell+36;
    s += '<g class="robot" transform="translate('+rx+' '+ry+')"><circle r="23" class="robot-face"/><text y="8" class="robot-letter" text-anchor="middle">R</text>'+animateMove(dx,dy)+'</g>';
    s += rect(515,100,390,320,18,'zone');
    s += text(710,138,'指令顺序','zone-title');
    (state.commands||[]).forEach(function(cmd,i){
      var col=i%4,row=Math.floor(i/4), xx=565+col*85, yy=205+row*96;
      s += rect(xx-30,yy-32,60,60,15,i===state.current?'instruction active':'instruction');
      s += text(xx,yy+11,cmd,'arrow-command');
      s += text(xx,yy+54,String(i+1),'tiny-label');
    });
    s += text(710,385,state.status==='blocked'?'停下：前方是障碍物':state.status==='done'?'到达终点':'一步一步执行','result-text');
    s += text(710,456,state.note||'向右永远表示地图右侧。','small-label');
    return svg(s,'五乘五方格地图上的机器人移动，包含起点、终点和障碍物');
  }
  function renderPixels(state) {
    var matrix=state.matrix||[], coarse=state.coarse||[], filled=state.filled==null?16:state.filled;
    var palette={'.':'#fffaf0','#':'#202f45','a':'#e5a14d','b':'#6f9a83','c':'#d67465'};
    var s=text(300,48,'较粗网格 · 4 × 4','zone-title')+text(690,48,'较细网格 · 8 × 8','zone-title');
    var size=54,startX=192,startY=95;
    for(var r=0;r<4;r++) for(var c=0;c<4;c++) {
      var idx=r*4+c, fill=idx<filled?palette[coarse[r][c]]:'#ffffff';
      var cls=idx>=Number(state.revealFrom||0)&&idx<filled?'pixel-cell pixel-reveal':'pixel-cell';
      s+=rect(startX+c*size,startY+r*size,size,size,0,cls,'fill="'+fill+'" style="--delay:'+(idx-Number(state.revealFrom||0))*100+'ms"');
    }
    var small=33, fx=555,fy=96;
    for(var rr=0;rr<8;rr++) for(var cc=0;cc<8;cc++) {
      var group=Math.floor(rr/2)*4+Math.floor(cc/2);
      var color=group<filled?palette[matrix[rr][cc]]:'#fff';
      var fcls=group>=Number(state.revealFrom||0)&&group<filled?'pixel-cell pixel-reveal':'pixel-cell';
      s+=rect(fx+cc*small,fy+rr*small,small,small,0,fcls,'fill="'+color+'" style="--delay:'+(group-Number(state.revealFrom||0))*100+'ms"');
    }
    if(state.highlight) s+=rect(fx+state.highlight[1]*2*small,fy+state.highlight[0]*2*small,small*2,small*2,2,'focus-outline');
    s+=text(300,360,'每个小格记录一种颜色','small-label')+text(690,390,'同一图案，格子更细','small-label');
    s+=rect(170,418,620,48,12,'info-strip')+text(480,449,state.note||'记录的单元更多，可以表示更多局部变化。','result-text');
    return svg(s,'由同一颜色矩阵生成的四乘四和八乘八像素图案');
  }
  function renderBubble(state) {
    var arr=state.cards||state.array||[], s=text(480,52,'相邻两张卡片比较数值大小','section-title');
    var x0=arr.length===6?70:150,w=arr.length===6?118:132,gap=arr.length===6?20:22;
    arr.forEach(function(card,i){
      var value=typeof card==='object'?card.value:card;
      var x=x0+i*(w+gap), active=i===state.left||i===state.right;
      var from=state.previousCards&&typeof card==='object'?state.previousCards.findIndex(function(prev){return prev.id===card.id;}):i;
      var dx=from>=0?(from-i)*(w+gap):0;
      s+='<g class="card-move">'+rect(x,180,w,145,18,active?'number-card compare':'number-card')+text(x+w/2,266,String(value),'number-value')+text(x+w/2,358,'位置 '+(i+1),'small-label')+animateMove(dx,0)+'</g>';
    });
    if(state.left!=null&&state.right!=null) {
      var lx=x0+state.left*(w+gap)+w/2,rx=x0+state.right*(w+gap)+w/2;
      s+=line(lx,130,rx,130,'compare-line','marker-end="url(#arrow)"');
      s+=text((lx+rx)/2,112,state.swap?'交换':'不交换','result-text');
    }
    s+=rect(190,410,580,54,12,'info-strip')+text(480,444,state.note||'从左向右，一轮一轮比较相邻项。','result-text');
    return svg(s,'数字卡片按冒泡排序过程比较并交换');
  }
  function renderNetwork(state) {
    var points={S:[105,255],A:[300,135],B:[300,375],C:[535,135],D:[535,375],T:[830,255]};
    var edges=[['S','A'],['S','B'],['A','C'],['A','D'],['B','D'],['C','D'],['C','T'],['D','T']];
    var s=text(480,42,'简化示意：数据块沿连接线前进','section-title');
    edges.forEach(function(e){var p=points[e[0]],q=points[e[1]],hot=(state.activeEdges||[]).some(function(a){return a[0]===e[0]&&a[1]===e[1];});s+=line(p[0],p[1],q[0],q[1],hot?'network-edge hot':'network-edge','marker-end="url(#arrow)"');});
    Object.keys(points).forEach(function(id){var p=points[id],end=id==='S'||id==='T';s+='<circle cx="'+p[0]+'" cy="'+p[1]+'" r="'+(end?45:34)+'" class="network-node '+(end?'endpoint':'')+'"/>'+text(p[0],p[1]+6,end?(id==='S'?'发送':'接收'):'节点 '+id,'node-label');});
    (state.packets||[]).forEach(function(pkt){var route=pkt.path||['S'];var pos=pkt.status==='arrived'?points.T:points[route[route.length-1]||'S'];var x=pos[0],y=pos[1]-54-(pkt.order||0)*52;var animation='';if(pkt.id===state.movingId&&!reducedMotion&&route.length>1){var path='';route.forEach(function(node,i){var p=points[node];path+=(i?' L':'M')+(p[0]-x)+' '+(p[1]-y);});if(route[route.length-1]!=='T'){var t=points.T;path+=' L'+(t[0]-x)+' '+(t[1]-y);}animation='<animateMotion path="'+path+'" dur="1.35s" fill="freeze"/>';}s+='<g>'+rect(x-48,y-20,96,38,10,'packet-box')+text(x,y+6,'块 '+pkt.id+'：'+pkt.chunk,'packet-label')+animation+'</g>';});
    s+=rect(230,450,500,44,12,'info-strip')+text(480,478,state.note||'接收端查看编号后按顺序重组。','result-text');
    return svg(s,'发送端、路由节点、接收端和编号消息块传输图');
  }
  function renderSearch(state) {
    var arr=state.array||[], s=text(480,46,'目标值：'+state.target,'section-title'), x0=65,cell=128;
    arr.forEach(function(v,i){var x=x0+i*cell,kind=i===state.current?'search-current':(state.checked||[]).indexOf(i)>=0?'search-checked':'search-cell';s+=rect(x,150,110,115,14,kind)+text(x+55,215,String(v),'number-value')+text(x+55,298,'第 '+(i+1)+' 项','small-label')+text(x+55,323,'下标 '+i,'tiny-label');});
    var code=[['i = 0','从第一项开始'],['比较 data[i] 与目标','检查当前项'],['相等则停止','找到目标'],['否则 i 加一','继续向后']];
    code.forEach(function(pair,i){s+=rect(190,365+i*31,580,27,7,i===state.codeLine?'code-active':'code-row')+text(225,384+i*31,pair[0],'code-text','start')+text(732,384+i*31,pair[1],'tiny-label','end');});
    s+=text(480,510,state.note||'位置从 1 开始说；下标从 0 开始数。','result-text');
    return svg(s,'线性查找逐项检查数组并高亮代码步骤');
  }
  function renderContainers(state) {
    var s=text(255,48,'栈：后进先出','zone-title')+text(705,48,'队列：先进先出','zone-title');
    s+=rect(85,82,340,350,18,state.focus==='stack'?'zone active':'zone');
    s+=rect(535,82,340,350,18,state.focus==='queue'?'zone active':'zone');
    s+=line(255,105,255,150,'pointer-line','marker-end="url(#arrow)"')+text(255,99,'栈顶','small-label');
    var st=state.stack||[];st.forEach(function(v,i){var y=378-i*70;s+=rect(155,y,200,58,10,i===st.length-1?'container-item top-item':'container-item')+text(255,y+38,v,'item-letter');});
    s+=text(255,422,'取出端在上方','tiny-label');
    s+=line(590,258,590,258,'pointer-line')+text(590,150,'队首：先离开','small-label');
    var q=state.queue||[];q.forEach(function(v,i){var x=580+i*88;s+=rect(x,216,76,76,12,i===0?'container-item top-item':'container-item')+text(x+38,263,v,'item-letter');});
    if(q.length) s+=text(836,198,'队尾：新加入','tiny-label');
    s+=text(705,340,'离开顺序：'+(state.queueOut||[]).join('、'),'result-text');
    s+=text(255,480,'离开顺序：'+(state.stackOut||[]).join('、'),'result-text');
    s+=rect(380,450,200,42,10,'info-strip')+text(480,478,state.note||'空结构没有东西可取。','small-label');
    return svg(s,'左侧栈顶取出顺序与右侧队列队首取出顺序对比');
  }
  function renderTraining(state) {
    var s=text(480,38,'小型合成二维样例 · 最近邻分类','section-title');
    var x0=155,y0=430,scale=106;
    s+=line(x0,y0,x0+530,y0,'axis')+line(x0,y0,x0,y0-350,'axis');
    [1,2,3,4,5].forEach(function(v){s+=line(x0+v*scale,y0-4,x0+v*scale,y0+4,'axis-tick')+text(x0+v*scale,y0+25,String(v),'tiny-label')+line(x0-4,y0-v*65,x0+4,y0-v*65,'axis-tick')+text(x0-22,y0-v*65+5,String(v),'tiny-label');});
    s+=text(435,485,'特征一','tiny-label')+text(104,250,'特征二','tiny-label');
    var coords=function(p){return [x0+p[0]*scale,y0-p[1]*65];};
    (state.train||[]).forEach(function(p){var a=coords(p.xy);s+=p.label==='红' ? '<circle cx="'+a[0]+'" cy="'+a[1]+'" r="12" class="point-red"/>' : rect(a[0]-11,a[1]-11,22,22,0,'point-blue');});
    if(state.test){var b=coords(state.test.xy);if(state.nearest){var q=coords(state.nearest.xy);s+=line(b[0],b[1],q[0],q[1],'nearest-line');}s+='<path d="M'+b[0]+' '+(b[1]-16)+' 16 16-16 16-16-16z" class="point-test"/>';s+=text(b[0]+36,b[1]-14,'待判断','small-label','start');}
    s+=rect(640,90,254,330,16,'info-strip')+text(767,132,state.phase==='train'?'训练样例':'新样例','zone-title');
    if(state.test) {
      s+=text(767,190,'最近样例：'+(state.nearest?state.nearest.label:'—'),'small-label');
      if(state.nearest) s+=text(767,214,'直线距离约 '+n(state.nearest.distance),'small-label');
      s+=text(767,236,'预测：'+(state.prediction||'待计算'),'result-text');
      if(state.truth) s+=text(767,279,'真实：'+state.truth,'result-text');
      if(state.correct!=null) s+=text(767,325,state.correct?'本次判断正确':'本次判断不同','result-text');
    } else {s+=text(767,195,'红色圆点：红类','small-label')+text(767,235,'蓝色方块：蓝类','small-label')+text(767,285,'只用训练样例找最近点','small-label');}
    s+=text(480,510,state.note||'先按距离预测，再揭开测试样例的真实类别。','result-text');
    return svg(s,'二维平面中的训练样例、最近邻连线和测试类别预测');
  }
  function renderGraph(state) {
    var pos={A:[160,160],B:[360,95],C:[360,275],D:[570,115],E:[570,325],F:[800,215]};
    var edges=lesson.data.edges||[], s=text(480,42,'边上的数字表示路程成本','section-title');
    edges.forEach(function(e){var a=pos[e[0]],b=pos[e[1]],key=e[0]+e[1],active=(state.relaxed||[]).indexOf(key)>=0,route=(state.routeEdges||[]).indexOf(key)>=0;s+=line(a[0],a[1],b[0],b[1],route?'graph-edge route':active?'graph-edge active':'graph-edge','');var mx=(a[0]+b[0])/2,my=(a[1]+b[1])/2;s+=rect(mx-21,my-17,42,28,8,'weight-chip')+text(mx,my+3,String(e[2]),'weight-label');});
    Object.keys(pos).forEach(function(id){var p=pos[id],d=state.distances&&state.distances[id];var status=(state.settled||[]).indexOf(id)>=0?'已确定':d==null?'未到达':'待检查';var active=id===state.selected;s+='<circle cx="'+p[0]+'" cy="'+p[1]+'" r="36" class="graph-node '+(active?'selected':'')+'"/>'+text(p[0],p[1]+6,id,'node-label')+text(p[0],p[1]+57,(d==null?'∞':n(d))+' · '+status,'tiny-label');});
    s+=rect(84,425,792,58,12,'info-strip')+text(480,460,state.note||'距离变短时，同时更新距离与前驱。','result-text');
    return svg(s,'六个节点的带权图与 Dijkstra 距离更新状态');
  }
  function renderGradient(state) {
    var s=text(480,40,'目标函数 f(x) = x²','section-title');
    var left=135,top=80,w=600,h=330,xmin=-8,xmax=8,ymax=50;
    var X=function(x){return left+(x-xmin)/(xmax-xmin)*w;},Y=function(y){return top+h-y/ymax*h;};
    s+=line(left,Y(0),left+w,Y(0),'axis')+line(X(0),top,X(0),top+h,'axis');
    [-8,-4,0,4,8].forEach(function(v){s+=line(X(v),Y(0)-5,X(v),Y(0)+5,'axis-tick')+text(X(v),Y(0)+25,String(v),'tiny-label');});
    [0,10,20,30,40,50].forEach(function(v){s+=line(X(0)-5,Y(v),X(0)+5,Y(v),'axis-tick')+text(X(0)-15,Y(v)+5,String(v),'tiny-label','end');});
    var path='';for(var i=0;i<=80;i++){var x=xmin+(xmax-xmin)*i/80;path+=(i?' L':'M')+X(x)+' '+Y(x*x);}
    s+='<path d="'+path+'" class="curve"/>';
    (state.points||[]).forEach(function(pt,i){var px=X(pt.x),py=Y(pt.y);if(i>0){var prev=state.points[i-1];s+=line(X(prev.x),Y(prev.y),px,py,'descent-line');}s+='<circle cx="'+px+'" cy="'+py+'" r="'+(i===state.points.length-1?10:7)+'" class="descent-point"/>';});
    var curr=state.current;if(curr){s+=text(798,145,'第 '+state.iteration+' 次更新','zone-title','middle')+text(798,203,'x = '+n(curr.x),'result-text')+text(798,244,'f(x) = '+n(curr.y),'result-text')+text(798,300,'方向：'+(curr.direction||'向最低点'),'small-label');}
    s+=text(435,470,'横轴是 x，纵轴是函数值 f(x)','small-label');
    s+=rect(170,488,620,28,8,'info-strip')+text(480,508,state.note||'步长过大时，下一点可能越过最低点。','tiny-label');
    return svg(s,'抛物线上的梯度下降点位根据真实公式逐步更新');
  }
  function renderMetrics(state) {
    var c=state.counts||{tp:0,fp:0,fn:0,tn:0};
    var s=text(480,35,'真实类别（行） × 预测类别（列）','section-title');
    s+=text(560,73,'预测：垃圾邮件','small-label')+text(790,73,'预测：正常邮件','small-label');
    s+=text(210,161,'真实：垃圾邮件','small-label','end')+text(210,311,'真实：正常邮件','small-label','end');
    var boxes=[
      {x:260,y:95,key:'tp',name:'真正例',explain:'垃圾信被拦下',c:'#e6b75f'},
      {x:500,y:95,key:'fn',name:'假负例 · 漏报',explain:'垃圾信放过去',c:'#d97968'},
      {x:260,y:245,key:'fp',name:'假正例 · 误报',explain:'正常信被拦下',c:'#d97968'},
      {x:500,y:245,key:'tn',name:'真负例',explain:'正常信正常通过',c:'#82a68b'}
    ];
    boxes.forEach(function(b){s+=rect(b.x,b.y,220,125,15,'metric-cell','fill="'+b.c+'"')+text(b.x+110,b.y+38,b.name,'metric-title')+text(b.x+110,b.y+78,String(c[b.key]||0),'metric-count')+text(b.x+110,b.y+105,b.explain,'tiny-label');});
    s+=rect(745,85,195,325,12,'metric-summary')+text(842,118,'阈值 '+n(state.threshold),'small-label')+text(842,148,'当前：'+(state.currentId||'全部'),'result-text');
    if(state.current){var t=state.current.truth==='spam'?'垃圾邮件':'正常邮件',p=state.current.predicted==='spam'?'垃圾邮件':'正常邮件';s+=text(842,185,'真实：'+t,'tiny-label')+text(842,215,'预测：'+p,'tiny-label')+text(842,245,'模拟分数 '+n(state.current.score),'tiny-label');}
    if(state.metrics){s+=text(842,292,'准确率 '+metricPct(state.metrics.accuracy),'tiny-label')+text(842,326,'精确率 '+metricPct(state.metrics.precision),'tiny-label')+text(842,360,'召回率 '+metricPct(state.metrics.recall),'tiny-label');}
    else s+=text(842,310,'逐条计数中…','tiny-label');
    if(state.compare){s+=text(842,386,'0.50：P '+metricPct(state.compare.firstMetrics.precision)+' / R '+metricPct(state.compare.firstMetrics.recall),'tiny-label')+text(842,405,'0.65：P '+metricPct(state.compare.secondMetrics.precision)+' / R '+metricPct(state.compare.secondMetrics.recall),'tiny-label');}
    s+=text(480,470,state.note||'逐个样例计数，指标稍后按总数计算。','result-text');
    return svg(s,'真实类别为行预测类别为列的混淆矩阵，显示垃圾邮件判断计数');
  }
  function mobileSvg(inner,label){return '<svg class="lesson-svg mobile-svg" viewBox="0 0 360 280" role="img" aria-label="'+esc(label)+'" xmlns="http://www.w3.org/2000/svg"><defs><marker id="arrow-m" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 8 4 0 8Z" fill="#61758a"/></marker></defs>'+inner+'</svg>';}
  function renderMobile(state){
    var s='', t=function(x,y,v,cls,anchor){return text(x,y,v,cls,anchor);};
    if(lesson.kind==='input-process-output'){
      s+=rect(8,80,100,112,14,'zone '+(state.stage==='input'?'active':''))+rect(128,80,104,112,14,'device-body')+rect(252,80,100,112,14,'zone '+(state.stage==='output'?'active':''));
      s+=t(58,68,'输入','small-label')+t(180,68,'处理','small-label')+t(302,68,'输出','small-label');
      s+=t(58,145,state.input||'按键 A','result-text')+t(180,145,'设备','device-title')+t(180,172,state.rule||'按规则','tiny-label')+t(302,145,state.output||'等待','result-text');
      s+=line(108,136,124,136,'flow-line','marker-end="url(#arrow-m)"')+line(232,136,248,136,'flow-line','marker-end="url(#arrow-m)"');
      s+=rect(270,153,64,25,6,'output-light');s+=t(180,235,'按键 A → 圆灯亮；按键 B → 三角灯亮','small-label');
    } else if(lesson.kind==='sorting-by-rule'){
      var cols=[65,180,295], names=state.rule==='color'?['红色','蓝色','黄色']:['圆形','三角形','方形'];
      if(state.stage==='pool'){
        s+=rect(12,65,336,145,14,'zone');s+=t(180,91,'待分类图形','zone-title');
        (state.items||[]).forEach(function(it,i){var x=55+(i%3)*125,y=138+Math.floor(i/3)*50;s+=tileShape(it.shape,{red:'#d66b61',blue:'#6c8db2',yellow:'#d8ae4c'}[it.color],x,y,31,it.colorName+it.shapeName);});
      }else names.forEach(function(name,k){s+=rect(6+k*116,65,112,150,12,'zone');s+=t(cols[k],91,name,'small-label');(state.groups[k]||[]).forEach(function(it,j){var x=cols[k],y=133+j*42;s+=tileShape(it.shape,{red:'#d66b61',blue:'#6c8db2',yellow:'#d8ae4c'}[it.color],x,y,28,it.colorName);});});
      s+=t(180,252,state.note||'换规则，同一批图形重新分组。','small-label');
    } else if(lesson.kind==='robot-instructions'){
      var x0=12,y0=65,cell=33;
      for(var r=0;r<5;r++)for(var c=0;c<5;c++){var xx=x0+c*cell,yy=y0+r*cell;s+=rect(xx,yy,cell,cell,2,'grid-cell');if(r===0&&c===0)s+=t(xx+16,yy+22,'起','tiny-label');if(r===0&&c===4)s+=t(xx+16,yy+22,'终','tiny-label');if((state.walls||[]).some(function(w){return w[0]===r&&w[1]===c;}))s+=rect(xx+3,yy+3,cell-6,cell-6,3,'wall-cell')+t(xx+16,yy+22,'障','tiny-label');}
      (state.path||[]).forEach(function(p){s+='<circle cx="'+(x0+p[1]*cell+16)+'" cy="'+(y0+p[0]*cell+16)+'" r="5" class="trail-dot"/>';});
      var rp=state.position||[0,0];s+='<circle cx="'+(x0+rp[1]*cell+16)+'" cy="'+(y0+rp[0]*cell+16)+'" r="11" class="robot-face"/>';
      s+=t(276,76,'指令','small-label');(state.commands||[]).forEach(function(c,i){s+=rect(214+(i%4)*36,92+Math.floor(i/4)*48,30,34,7,i===state.current?'instruction active':'instruction')+t(229+(i%4)*36,117+Math.floor(i/4)*48,c,'arrow-command');});
      s+=t(275,213,state.status==='blocked'?'遇障停止':state.status==='done'?'到达终点':'逐格移动','small-label')+t(180,267,state.note||'箭头按顺序执行。','tiny-label');
    } else if(lesson.kind==='pixels-build-picture'){
      var pal={'.':'#fffaf0','#':'#202f45','a':'#e5a14d','b':'#6f9a83','c':'#d67465'},coarse=state.coarse||[],matrix=state.matrix||[],filled=state.filled==null?16:state.filled;
      s+=t(91,42,'4×4 粗网格','small-label')+t(263,42,'8×8 细网格','small-label');
      for(var a=0;a<4;a++)for(var b=0;b<4;b++){var ix=a*4+b;s+=rect(22+b*34,56+a*34,34,34,0,'pixel-cell','fill="'+(ix<filled?pal[coarse[a][b]]:'#fff')+'"');}
      for(var rr=0;rr<8;rr++)for(var cc=0;cc<8;cc++){var gr=Math.floor(rr/2)*4+Math.floor(cc/2);s+=rect(185+cc*19,56+rr*19,19,19,0,'pixel-cell','fill="'+(gr<filled?pal[matrix[rr][cc]]:'#fff')+'"');}
      if(state.highlight)s+=rect(185+state.highlight[1]*2*19,56+state.highlight[0]*2*19,38,38,2,'focus-outline');
      s+=t(180,244,state.note||'同一图案，颜色单元数量不同。','small-label');
    } else if(lesson.kind==='cards-bubble-sort'){
      var arr=state.cards||state.array||[];s+=t(180,48,'只比较相邻两张卡片','small-label');
      arr.forEach(function(card,i){var v=typeof card==='object'?card.value:card,x=12+i*69,from=state.previousCards&&typeof card==='object'?state.previousCards.findIndex(function(p){return p.id===card.id;}):i,dx=from>=0?(from-i)*69:0;s+='<g>'+rect(x,94,61,78,11,i===state.left||i===state.right?'number-card compare':'number-card')+t(x+30,145,String(v),'number-value')+animateMove(dx,0)+'</g>';});
      if(state.left!=null)s+=t(180,206,state.swap?'需要交换':'不需要交换','result-text');
      s+=t(180,250,state.note||'每一轮把较大的数向后移动。','tiny-label');
    } else if(lesson.kind==='message-packets'){
      var pts={S:[35,128],A:[126,78],B:[126,184],C:[225,78],D:[225,184],T:[325,128]},edges=[['S','A'],['S','B'],['A','C'],['A','D'],['B','D'],['C','D'],['C','T'],['D','T']];
      edges.forEach(function(e){var a=pts[e[0]],b=pts[e[1]];s+=line(a[0],a[1],b[0],b[1],'network-edge','marker-end="url(#arrow-m)"');});
      Object.keys(pts).forEach(function(id){var p=pts[id];s+='<circle cx="'+p[0]+'" cy="'+p[1]+'" r="'+(id==='S'||id==='T'?21:16)+'" class="network-node"/>'+t(p[0],p[1]+5,id==='S'?'发':id==='T'?'收':id,'tiny-label');});
      (state.packets||[]).forEach(function(p,i){var x=14+i*110,y=222,anim='';if(p.id===state.movingId&&!reducedMotion&&p.path){var mp={S:[35,128],A:[126,78],B:[126,184],C:[225,78],D:[225,184],T:[325,128]},path='';p.path.forEach(function(id,j){var pt=mp[id];path+=(j?' L':'M')+(pt[0]-(x+51))+' '+(pt[1]-(y+18));});if(p.path[p.path.length-1]!=='T')path+=' L'+(325-(x+51))+' '+(128-(y+18));anim='<animateMotion path="'+path+'" dur="1.35s" fill="freeze"/>';}s+='<g>'+rect(x,y,102,36,8,'packet-box')+t(x+51,y+24,p.id+' '+p.chunk,'tiny-label')+anim+'</g>';});
      s+=t(180,274,state.note||'按编号重组。','tiny-label');
    } else if(lesson.kind==='linear-search'){
      s+=t(180,40,'目标 '+state.target,'section-title');var ar=state.array||[];
      ar.forEach(function(v,i){var x=6+i*58,cl=i===state.current?'search-current':(state.checked||[]).indexOf(i)>=0?'search-checked':'search-cell';s+=rect(x,65,54,58,7,cl)+t(x+27,103,String(v),'result-text')+t(x+27,145,String(i),'tiny-label');});
      s+=t(180,176,state.current==null?(state.note||'停止检查，不越界。'):'检查第 '+(state.current+1)+' 项，下标 '+state.current,'small-label');
      s+=rect(24,202,312,54,10,'info-strip')+t(180,224,'比较当前项 → 相等则停止','tiny-label')+t(180,246,'否则下标加一，继续向后','tiny-label');
    } else if(lesson.kind==='stack-and-queue'){
      s+=rect(5,48,166,175,12,state.focus==='stack'?'zone active':'zone')+rect(189,48,166,175,12,state.focus==='queue'?'zone active':'zone');s+=t(88,73,'栈顶','small-label')+t(272,73,'队首 → 队尾','small-label');
      (state.stack||[]).forEach(function(v,i){var y=184-i*34;s+=rect(42,y-28,92,28,5,'container-item')+t(88,y-8,v,'small-label');});
      (state.queue||[]).forEach(function(v,i){var x=198+i*47;s+=rect(x,121,42,42,7,'container-item')+t(x+21,148,v,'small-label');});
      s+=t(88,214,'出栈 '+((state.stackOut||[]).join('、')||'—'),'tiny-label')+t(272,214,'出队 '+((state.queueOut||[]).join('、')||'—'),'tiny-label')+t(180,257,state.note||'栈后进先出；队列先进先出。','tiny-label');
    } else if(lesson.kind==='training-and-testing'){
      var ox=28,oy=205,sc=37,xy=function(p){return[ox+p[0]*sc,oy-p[1]*27];};s+=line(ox,oy,220,oy,'axis')+line(ox,oy,ox,52,'axis');
      (state.train||[]).forEach(function(p){var q=xy(p.xy);s+=p.label==='红'?'<circle cx="'+q[0]+'" cy="'+q[1]+'" r="7" class="point-red"/>':rect(q[0]-6,q[1]-6,12,12,0,'point-blue');});
      if(state.test){var q=xy(state.test.xy);if(state.nearest){var p=xy(state.nearest.xy);s+=line(q[0],q[1],p[0],p[1],'nearest-line');}s+='<path d="M'+q[0]+' '+(q[1]-10)+' 10 10-10 10-10-10z" class="point-test"/>';}
      s+=rect(236,60,116,172,10,'info-strip')+t(294,88,state.test?state.test.id:'训练','small-label');if(state.nearest)s+=t(294,113,'距离 '+n(state.nearest.distance),'tiny-label');s+=t(294,143,'预测 '+(state.prediction||'—'),'tiny-label');if(state.truth)s+=t(294,169,'真实 '+state.truth,'tiny-label');if(state.correct!=null)s+=t(294,193,state.correct?'判断正确':'判断不同','tiny-label');if(state.correct!=null)s+=t(294,218,'正确 '+state.correct+' / '+(state.total||3),'tiny-label');
      s+=t(180,257,state.note||'距离最近的训练点提供预测类别。','tiny-label');
    } else if(lesson.kind==='shortest-path'){
      var pos={A:[28,125],B:[105,63],C:[105,205],D:[210,63],E:[210,205],F:[330,125]},edges=lesson.data.edges||[];
      edges.forEach(function(e){var a=pos[e[0]],b=pos[e[1]],key=e[0]+e[1],cl=(state.routeEdges||[]).indexOf(key)>=0?'graph-edge route':'graph-edge';s+=line(a[0],a[1],b[0],b[1],cl);s+=t((a[0]+b[0])/2,(a[1]+b[1])/2-5,String(e[2]),'tiny-label');});
      Object.keys(pos).forEach(function(id){var p=pos[id],d=state.distances&&state.distances[id];s+='<circle cx="'+p[0]+'" cy="'+p[1]+'" r="17" class="graph-node '+(state.selected===id?'selected':'')+'"/>'+t(p[0],p[1]+6,id,'tiny-label')+t(p[0],p[1]+34,d==null?'∞':String(d),'tiny-label');});
      s+=t(180,265,state.note||'候选距离 = 已知距离 + 边权。','tiny-label');
    } else if(lesson.kind==='gradient-descent'){
      var left=18,top=45,w=205,h=160,xmin=-8,xmax=8,ymax=50,X=function(x){return left+(x-xmin)/(xmax-xmin)*w;},Y=function(y){return top+h-y/ymax*h;};s+=line(left,Y(0),left+w,Y(0),'axis')+line(X(0),top,X(0),top+h,'axis');var path='';for(var i=0;i<=48;i++){var xx=xmin+(xmax-xmin)*i/48;path+=(i?' L':'M')+X(xx)+' '+Y(xx*xx);}s+='<path d="'+path+'" class="curve"/>';
      (state.points||[]).forEach(function(p,i){s+='<circle cx="'+X(p.x)+'" cy="'+Y(p.y)+'" r="'+(i===state.points.length-1?6:4)+'" class="descent-point"/>';});
      if(state.current){s+=rect(235,62,118,132,10,'info-strip')+t(294,91,'第 '+state.iteration+' 次','small-label')+t(294,127,'x '+n(state.current.x),'tiny-label')+t(294,158,'f(x) '+n(state.current.y),'tiny-label');}
      s+=t(180,250,state.note||'x ← x − α × 2x','tiny-label');
    } else if(lesson.kind==='classification-metrics'){
      var c=state.counts||{tp:0,fp:0,fn:0,tn:0};s+=t(180,30,'真实类别行 · 预测类别列','tiny-label')+t(113,54,'预测垃圾','tiny-label')+t(249,54,'预测正常','tiny-label');
      s+=t(20,119,'真实垃圾','tiny-label','start')+t(20,201,'真实正常','tiny-label','start');
      var box=[['tp','真正例',74,70,'#e6b75f'],['fn','假负例',210,70,'#d97968'],['fp','假正例',74,151,'#d97968'],['tn','真负例',210,151,'#82a68b']];
      box.forEach(function(b){s+=rect(b[2],b[3],126,70,8,'metric-cell','fill="'+b[4]+'"')+t(b[2]+63,b[3]+24,b[1],'tiny-label')+t(b[2]+63,b[3]+56,String(c[b[0]]||0),'result-text');});
      s+=t(180,236,'阈值 '+n(state.threshold)+' · '+(state.currentId||''),'tiny-label');
      if(state.compare){s+=t(180,256,'0.50 精确 '+metricPct(state.compare.firstMetrics.precision)+' · 召回 '+metricPct(state.compare.firstMetrics.recall),'tiny-label')+t(180,276,'0.65 精确 '+metricPct(state.compare.secondMetrics.precision)+' · 召回 '+metricPct(state.compare.secondMetrics.recall),'tiny-label');}
      else if(state.metrics)s+=t(180,266,'准确 '+metricPct(state.metrics.accuracy)+' · 精确 '+metricPct(state.metrics.precision)+' · 召回 '+metricPct(state.metrics.recall),'tiny-label');
      else s+=t(180,266,'逐条计算；模拟分数','tiny-label');
    }
    return mobileSvg(s,lesson.title+'：当前教学步骤图示');
  }
  function render(state) {
    lastState=state;
    if(window.matchMedia&&window.matchMedia('(max-width: 520px)').matches)return renderMobile(state);
    switch (lesson.kind) {
      case 'input-process-output': return renderInput(state);
      case 'sorting-by-rule': return renderSorting(state);
      case 'robot-instructions': return renderRobot(state);
      case 'pixels-build-picture': return renderPixels(state);
      case 'cards-bubble-sort': return renderBubble(state);
      case 'message-packets': return renderNetwork(state);
      case 'linear-search': return renderSearch(state);
      case 'stack-and-queue': return renderContainers(state);
      case 'training-and-testing': return renderTraining(state);
      case 'shortest-path': return renderGraph(state);
      case 'gradient-descent': return renderGradient(state);
      case 'classification-metrics': return renderMetrics(state);
      default: return svg(text(480,260,'课件状态无效','result-text'),'课件画面');
    }
  }
  function fitEmbeddedVisual() {
    if (!embedded || practiceOpen) return;
    var image=stageNode.querySelector('svg');
    if (!image) return;
    var bounds=image.getBBox(), padding=24;
    if (bounds.width>0 && bounds.height>0 && [bounds.x,bounds.y,bounds.width,bounds.height].every(Number.isFinite)) {
      image.setAttribute('viewBox',[bounds.x-padding,bounds.y-padding,bounds.width+padding*2,bounds.height+padding*2].join(' '));
      image.setAttribute('preserveAspectRatio','xMidYMid meet');
    }
  }
  function renderStep(step) {
    lastState=step.state;
    stageNode.innerHTML = render(step.state);
    var display=step;
    if(hostReady&&hostContext){
      var sid='scene-'+String(index+1).padStart(2,'0');
      var hostScene=(hostContext.scenes||[]).find(function(item){return item.id===sid;});
      var hostPrompt=(hostContext.prompts||[]).find(function(item){return item.id===sid+'-read'&&item.scene_id===sid;});
      display={title:hostScene&&hostScene.title||step.title,text:hostPrompt&&hostPrompt.text||step.text};
    }
    captionNode.textContent = display.text;
    currentNode.textContent = '第 ' + (index+1) + ' 段 / 共 ' + lesson.steps.length + ' 段 · ' + display.title;
    practiceButton.disabled = embedded;
    return new Promise(function(resolve){requestAnimationFrame(function(){fitEmbeddedVisual();requestAnimationFrame(resolve);});});
  }
  function clearTimer() { if(timer!==null){window.clearTimeout(timer);timer=null;} }
  function stopSpeech() { if(window.speechSynthesis){try{window.speechSynthesis.cancel();}catch(_){}} }
  function voiceChoice() {
    if(!window.speechSynthesis) return null;
    var voices=window.speechSynthesis.getVoices()||[];
    var mainland=voices.filter(function(v){return /^(zh-CN|zh-Hans)(-|$)/i.test(v.lang||'')&&!/zh-(HK|TW)/i.test(v.lang||'');});
    mainland.sort(function(a,b){return (/^zh-CN/i.test(b.lang)?1:0)-(/^zh-CN/i.test(a.lang)?1:0);});
    return mainland[0]||null;
  }
  function waitForLateVoice(token) {
    var ready=voiceChoice();
    if(ready || !window.speechSynthesis) return Promise.resolve(ready);
    return new Promise(function(resolve){
      var done=false;
      function finish(){if(done)return;done=true;window.clearTimeout(fallback);window.speechSynthesis.removeEventListener('voiceschanged',changed);resolve(voiceChoice());}
      function changed(){finish();}
      var fallback=window.setTimeout(finish,1100);
      window.speechSynthesis.addEventListener('voiceschanged',changed,{once:true});
      voicesChangeHandler=changed;
      if(token!==generation) finish();
    });
  }
  function readingMs(value) { return Math.max(3600,Math.min(30000,Array.from(value).length*250/rateValue)); }
  function advanceAfter(token) {
    if(token!==generation || (mode!=='playing'&&mode!=='reading')) return;
    mode='gap';
    statusNode.textContent='本段结束，稍作停留';
    clearTimer();
    timer=window.setTimeout(function(){timer=null;if(token!==generation)return;if(index+1<lesson.steps.length)runStep(index+1);else finishPlayback();},700);
  }
  function silentStep(token,message) {
    if(token!==generation||mode!=='playing')return;
    mode='reading';
    statusNode.textContent=message;
    var duration=readingMs(lesson.steps[index].text);
    clearTimer();
    timer=window.setTimeout(function(){timer=null;advanceAfter(token);},duration);
  }
  async function speakCurrent(token) {
    if(token!==generation||mode!=='playing')return;
    var mute=byId('mute').checked;
    if(mute){silentStep(token,'静音播放：按字幕阅读时间自动继续');return;}
    var voice=await waitForLateVoice(token);
    if(token!==generation||mode!=='playing')return;
    if(!voice){silentStep(token,window.speechSynthesis?'没有普通话声音，按字幕阅读时间自动继续':'浏览器没有朗读接口，按字幕阅读时间自动继续');return;}
    try {
      var utterance=new SpeechSynthesisUtterance(lesson.steps[index].text);
      utterance.lang=voice.lang;
      utterance.voice=voice;
      utterance.rate=rateValue;
      utterance.onstart=function(){if(token===generation&&mode==='playing')statusNode.textContent='正在朗读本段';};
      utterance.onend=function(){if(token===generation&&mode==='playing')advanceAfter(token);};
      utterance.onerror=function(){if(token===generation&&mode==='playing')silentStep(token,'朗读未能继续，按字幕阅读时间自动播放');};
      statusNode.textContent='正在准备普通话声音';
      window.speechSynthesis.speak(utterance);
    } catch(_){silentStep(token,'朗读未能启动，按字幕阅读时间自动播放');}
  }
  async function runStep(next) {
    clearTimer();
    var token=++generation;
    document.body.classList.add('autoplay-active');
    stopSpeech();
    index=next;
    mode='playing';
    pauseButton.textContent='暂停';
    pauseButton.disabled=false;
    replayButton.disabled=false;
    restartButton.disabled=false;
    beginButton.hidden=true;
    byId('finished').hidden=true;
    await renderStep(lesson.steps[index]);
    if(token!==generation||mode!=='playing')return;
    await speakCurrent(token);
  }
  function finishPlayback() {
    clearTimer();
    mode='ended';
    statusNode.textContent='播放完了';
    captionNode.textContent=lesson.steps[lesson.steps.length-1].text;
    pauseButton.disabled=true;
    pauseButton.textContent='已结束';
    byId('finished').hidden=false;
  }
  function startFrom(next) {
    if(embedded)return;
    clearTimer();
    stopSpeech();
    byId('practice-panel').hidden=true;
    practiceOpen=false;
    practiceButton.textContent='自己试一试';
    runStep(next);
  }
  function pausePlayback() {
    if(mode!=='playing'&&mode!=='reading'&&mode!=='gap')return;
    var wasSpeaking=statusNode.textContent==='正在朗读本段'||statusNode.textContent==='正在准备普通话声音';
    generation++;
    clearTimer();
    stopSpeech();
    mode='paused';
    pauseButton.textContent='继续';
    statusNode.textContent='已暂停；继续时从本段开头重新播放';
    document.body.classList.add('is-paused');
    var activeSvg=stageNode.querySelector('svg');if(activeSvg&&activeSvg.pauseAnimations)activeSvg.pauseAnimations();
    if(!wasSpeaking && mode==='paused') { /* Timer-based reading and gap are cancelled above. */ }
  }
  function resumePlayback() {
    if(mode==='paused') {document.body.classList.remove('is-paused');var activeSvg=stageNode.querySelector('svg');if(activeSvg&&activeSvg.unpauseAnimations)activeSvg.unpauseAnimations();runStep(index);}
  }
  function initialPractice() {
    switch(lesson.kind){
      case 'input-process-output':return {input:'按键 A'};
      case 'sorting-by-rule':return {rule:'shape'};
      case 'robot-instructions':return {route:'correct'};
      case 'pixels-build-picture':return {size:4};
      case 'cards-bubble-sort':return {values:lesson.data.values.slice()};
      case 'message-packets':return {order:'2,3,1'};
      case 'linear-search':return {target:9};
      case 'stack-and-queue':return {kind:'stack',items:[],removed:[]};
      case 'training-and-testing':return {testIndex:0};
      case 'shortest-path':return {start:'A',end:'F'};
      case 'gradient-descent':return {alpha:0.15};
      case 'classification-metrics':return {threshold:0.5};
      default:return {};
    }
  }
  function practiceControls() {
    var host=byId('practice-controls'), kind=lesson.kind, html='';
    if(kind==='input-process-output') html='<button data-action="inputA">按键 A</button><button data-action="inputB">按键 B</button>';
    else if(kind==='sorting-by-rule') html='<button data-rule="shape">按形状分</button><button data-rule="color">按颜色分</button>';
    else if(kind==='robot-instructions') html='<button data-route="correct">播放正确路线</button><button data-route="wrong">检查错误路线</button>';
    else if(kind==='pixels-build-picture') html='<button data-size="4">较粗 4×4</button><button data-size="8">较细 8×8</button>';
    else if(kind==='cards-bubble-sort') html='<label>输入 3 到 6 个 0–99 的数 <input id="sort-input" value="'+esc(practice.values.join(','))+'" inputmode="numeric" aria-label="输入待排序数字，用逗号分隔"></label><button data-action="sort">运行排序</button>';
    else if(kind==='message-packets') html='<button data-order="2,3,1">路线甲：2、3、1 到达</button><button data-order="1,2,3">路线乙：1、2、3 到达</button>';
    else if(kind==='linear-search') html='<label>目标数值 <input id="search-target" type="number" min="0" max="99" value="'+practice.target+'" aria-label="线性查找目标"></label><button data-action="search">开始查找</button>';
    else if(kind==='stack-and-queue') html='<button data-kind="stack">练习栈</button><button data-kind="queue">练习队列</button><button data-action="push">加入 A/B/C</button><button data-action="pop">取出一个</button><button data-action="clear">清空练习</button>';
    else if(kind==='training-and-testing') html='<button data-test="0">测试点甲</button><button data-test="1">测试点乙</button><button data-test="2">测试点丙</button>';
    else if(kind==='shortest-path') html='<label>起点 <select id="path-start" aria-label="起点"></select></label><label>终点 <select id="path-end" aria-label="终点"></select></label><button data-action="path">计算路线</button>';
    else if(kind==='gradient-descent') html='<label>学习步长 <select id="alpha" aria-label="学习步长"><option value="0.05">0.05</option><option value="0.15">0.15</option><option value="0.6">0.60</option><option value="1.1">1.10</option></select></label><button data-action="gradient">比较 6 次更新</button>';
    else if(kind==='classification-metrics') html='<label>阈值 0.35–0.90 <input id="threshold" type="number" min="0.35" max="0.90" step="0.05" value="'+practice.threshold+'" aria-label="分类阈值"></label><button data-action="metrics">重新计算</button>';
    host.innerHTML=html;
    if(kind==='shortest-path'){
      var nodes=lesson.data.nodes||[];
      ['path-start','path-end'].forEach(function(id){var sel=byId(id);sel.innerHTML=nodes.map(function(v){return '<option value="'+v+'">'+v+'</option>';}).join('');});
      byId('path-start').value=practice.start;byId('path-end').value=practice.end;
    }
    if(kind==='gradient-descent')byId('alpha').value=String(practice.alpha);
    host.querySelectorAll('button').forEach(function(b){b.addEventListener('click',handlePractice);});
    host.querySelectorAll('input,select').forEach(function(el){el.addEventListener('change',function(){byId('practice-error').textContent='';});});
  }
  function setPracticeResult(state,message) {
    byId('practice-error').textContent='';
    byId('practice-output').textContent=message;
    byId('practice-visual').innerHTML=render(state);
  }
  function invalidPractice(message){byId('practice-error').textContent=message;}
  function grouping(items,rule) {
    var order=rule==='shape'?['circle','triangle','square']:['red','blue','yellow'];
    return order.map(function(k){return items.filter(function(v){return rule==='shape'?v.shape===k:v.color===k;});});
  }
  // Only confirmed controls become account checkpoints. Never persist generated SVG.
  function handlePractice(event) {
    var b=event.currentTarget, kind=lesson.kind;
    if(kind==='input-process-output')practice.input=b.dataset.action==='inputB'?'按键 B':'按键 A';
    else if(kind==='sorting-by-rule')practice.rule=b.dataset.rule;
    else if(kind==='robot-instructions')practice.route=b.dataset.route;
    else if(kind==='pixels-build-picture')practice.size=Number(b.dataset.size);
    else if(kind==='cards-bubble-sort'){
      var raw=(byId('sort-input').value||'').split(',').map(function(x){return x.trim();});
      if(raw.length<3||raw.length>6||raw.some(function(x){return !/^\d{1,2}$/.test(x)||Number(x)>99;})){invalidPractice('请输入 3 到 6 个 0–99 的整数，使用逗号分开。原有结果已保留。');return;}
      practice.values=raw.map(Number);
    } else if(kind==='message-packets')practice.order=b.dataset.order;
    else if(kind==='linear-search'){
      var rawTarget=byId('search-target').value, val=Number(rawTarget);
      if(!rawTarget.trim()||!Number.isInteger(val)||val<0||val>99){invalidPractice('目标请填 0 到 99 的整数。原有结果已保留。');return;}
      practice.target=val;
    } else if(kind==='stack-and-queue'){
      if(b.dataset.kind){practice.kind=b.dataset.kind;practice.items=[];practice.removed=[];}
      if(b.dataset.action==='clear'){practice.items=[];practice.removed=[];}
      if(b.dataset.action==='push'){
        if(practice.items.length>=3){invalidPractice('练习容器最多放 3 个项目。');return;}
        practice.items.push(['A','B','C'][practice.items.length]);
      }
      if(b.dataset.action==='pop'){
        if(!practice.items.length){invalidPractice('容器已空，不能继续取出。');return;}
        practice.removed.push(practice.kind==='queue'?practice.items.shift():practice.items.pop());
        practice.removed=practice.removed.slice(-100);
      }
    } else if(kind==='training-and-testing')practice.testIndex=Number(b.dataset.test);
    else if(kind==='shortest-path'){
      var start=byId('path-start').value,end=byId('path-end').value;
      if(lesson.data.nodes.indexOf(start)<0||lesson.data.nodes.indexOf(end)<0){invalidPractice('请选择图中的起点与终点。');return;}
      practice.start=start;practice.end=end;
    } else if(kind==='gradient-descent'){
      var alpha=Number(byId('alpha').value);
      if([0.05,0.15,0.6,1.1].indexOf(alpha)<0){invalidPractice('请选择已有的学习步长。');return;}
      practice.alpha=alpha;
    } else if(kind==='classification-metrics'){
      var rawThreshold=byId('threshold').value, th=Number(rawThreshold);
      if(!rawThreshold.trim()||!Number.isFinite(th)||th<0.35||th>0.9){invalidPractice('阈值请在 0.35 到 0.90 之间。原有结果已保留。');return;}
      practice.threshold=th;
    }
    practice.operated=true;restoreNotice='';showPractice();savePractice();
  }
  function practiceResult() {
    var kind=lesson.kind, state=practiceState(), message='选择一个操作，观察结果。';
    if(!practice.operated)return {state:state,message:message};
    if(kind==='input-process-output')message='手动输入“'+practice.input+'”，设备按已写好的规则显示“'+state.output+'”。';
    else if(kind==='sorting-by-rule')message='当前按照'+(practice.rule==='shape'?'形状':'颜色')+'分类，共分成 '+state.groups.length+' 组。';
    else if(kind==='robot-instructions')message='指令检查：'+(state.status==='done'?'到达终点。':state.status==='blocked'?'第 '+(state.current+1)+' 条指令遇到障碍，已经停止。':'还没有到达终点。');
    else if(kind==='pixels-build-picture')message='当前显示 '+practice.size+'×'+practice.size+' 网格。方格数量是 4×4 的 16 个与 8×8 的 64 个。';
    else if(kind==='cards-bubble-sort')message='排序完成：['+state.array.join(', ')+']。原数组中的数值没有增加或丢失。';
    else if(kind==='message-packets')message='到达顺序 '+practice.order.split(',').join('、')+'；按块编号重组：'+lesson.data.message+'。';
    else if(kind==='linear-search')message=state.current!==null?'找到 '+practice.target+'：第 '+(state.current+1)+' 项，下标 '+state.current+'。':'检查完全部 '+lesson.data.array.length+' 项，没有找到 '+practice.target+'。';
    else if(kind==='stack-and-queue')message=(practice.kind==='stack'?'栈':'队列')+'当前有 '+practice.items.length+' 个项目。取出记录：'+(practice.removed.join('、')||'无')+'。';
    else if(kind==='training-and-testing')message='预测 '+state.prediction+'，真实类别 '+state.truth+'；'+(state.correct?'本次正确。':'本次不同。');
    else if(kind==='shortest-path')message=state.path.length?'最短路径 '+state.path.join(' → ')+'，总成本 '+state.distances[practice.end]+'。':'从 '+practice.start+' 无法到达 '+practice.end+'。';
    else if(kind==='gradient-descent')message='步长 '+practice.alpha+'：第 6 次后 x = '+n(state.current.x)+'，f(x) = '+n(state.current.y)+'。';
    else if(kind==='classification-metrics'){var m=state.counts;message='TP='+m.tp+'，FP='+m.fp+'，FN='+m.fn+'，TN='+m.tn+'；精确率 '+pct(safeDiv(m.tp,m.tp+m.fp))+'，召回率 '+pct(safeDiv(m.tp,m.tp+m.fn))+'。';}
    return {state:state,message:message};
  }
  function showPractice(){
    var result=practiceResult();setPracticeResult(result.state,result.message);
    if(embedded)stageNode.innerHTML=render(result.state);
    if(restoreNotice)byId('practice-error').textContent=restoreNotice;
  }
  function savePractice(){
    var token=++practiceRevision;
    if(!embedded||!window.K12.checkpoint){saveNotice.textContent='独立打开：实验只保留在当前页面，未保存到账号。';return;}
    saveNotice.textContent='正在保存实验到账号…';
    var state={state_version:1,content_key:'autoplay-'+lesson.key,practice:JSON.parse(JSON.stringify(practice))};
    window.K12.checkpoint.save(state).then(function(){if(token===practiceRevision)saveNotice.textContent='实验已保存到账号';},function(){if(token===practiceRevision)saveNotice.textContent='实验未保存，当前画面已保留；请使用平台的“重试保存”。';});
  }
  function restorePractice(state){
    if(!state||Object.keys(state).length===0)return;
    var p=state.practice, defaults=initialPractice();
    var keys=Object.keys(defaults).concat('operated');
    var object=function(v){return v&&typeof v==='object'&&!Array.isArray(v);};
    var valid=object(state)&&state.state_version===1&&state.content_key==='autoplay-'+lesson.key&&Object.keys(state).sort().join(',')==='content_key,practice,state_version'&&object(p)&&Object.keys(p).sort().join(',')===keys.sort().join(',')&&typeof p.operated==='boolean';
    var oneOf=function(v,a){return a.indexOf(v)>=0;};
    var integer=function(v,min,max){return Number.isInteger(v)&&v>=min&&v<=max;};
    if(valid)switch(lesson.kind){
      case 'input-process-output':valid=oneOf(p.input,['按键 A','按键 B']);break;
      case 'sorting-by-rule':valid=oneOf(p.rule,['shape','color']);break;
      case 'robot-instructions':valid=oneOf(p.route,['correct','wrong']);break;
      case 'pixels-build-picture':valid=oneOf(p.size,[4,8]);break;
      case 'cards-bubble-sort':valid=Array.isArray(p.values)&&p.values.length>=3&&p.values.length<=6&&p.values.every(function(v){return integer(v,0,99);});break;
      case 'message-packets':valid=oneOf(p.order,['2,3,1','1,2,3']);break;
      case 'linear-search':valid=integer(p.target,0,99);break;
      case 'stack-and-queue':valid=oneOf(p.kind,['stack','queue'])&&Array.isArray(p.items)&&p.items.length<=3&&Array.isArray(p.removed)&&p.removed.length<=100&&p.items.concat(p.removed).every(function(v){return oneOf(v,['A','B','C']);});break;
      case 'training-and-testing':valid=integer(p.testIndex,0,lesson.data.tests.length-1);break;
      case 'shortest-path':valid=oneOf(p.start,lesson.data.nodes)&&oneOf(p.end,lesson.data.nodes);break;
      case 'gradient-descent':valid=oneOf(p.alpha,[0.05,0.15,0.6,1.1]);break;
      case 'classification-metrics':valid=typeof p.threshold==='number'&&Number.isFinite(p.threshold)&&p.threshold>=0.35&&p.threshold<=0.9;break;
      default:valid=false;
    }
    if(valid){practice=JSON.parse(JSON.stringify(p));saveNotice.textContent='已恢复账号中的实验';}
    else {restoreNotice='保存的实验状态与本课件不兼容，已使用默认值；请重新操作后保存。';saveNotice.textContent=restoreNotice;}
  }
  function openPractice() {
    if(embedded)return;
    if(mode==='playing'||mode==='reading'||mode==='gap')pausePlayback();
    practiceOpen=!practiceOpen;
    byId('practice-panel').hidden=!practiceOpen;
    practiceButton.textContent=practiceOpen?'收起练习':'自己试一试';
    if(practiceOpen){practiceControls();showPractice();if(!window.K12)saveNotice.textContent='独立打开：实验只保留在当前页面，未保存到账号。';}
  }
  function simulateRobot(commands,walls,goal) {
    var pos=[0,0],path=[[0,0]],previous=[0,0],status='ready',current=0;
    var moves={'→':[0,1],'↓':[1,0],'←':[0,-1],'↑':[-1,0]};
    for(var i=0;i<commands.length;i++){
      current=i+1;previous=pos.slice();var d=moves[commands[i]],next=[pos[0]+d[0],pos[1]+d[1]];
      if(next[0]<0||next[0]>4||next[1]<0||next[1]>4){status='blocked';break;}
      if(walls.some(function(w){return w[0]===next[0]&&w[1]===next[1];})){status='blocked';break;}
      pos=next;path.push(pos.slice());
      if(pos[0]===goal[0]&&pos[1]===goal[1]){status='done';break;}
    }
    return {walls:walls,goal:goal,position:pos,previous:previous,path:path,commands:commands,current:Math.min(current-1,commands.length-1),status:status,note:status==='blocked'?'遇到障碍或边界时停止。':status==='done'?'到达目标格。':'路线还未结束。'};
  }
  function nearest(xy,train) {
    var best=null,bd=Infinity;
    train.forEach(function(p){var d=Math.pow(xy[0]-p.xy[0],2)+Math.pow(xy[1]-p.xy[1],2);if(d<bd){bd=d;best=p;}});
    return best?Object.assign({},best,{distance:Math.sqrt(bd),distanceSquared:bd}):null;
  }
  function bubbleSortValues(values){var a=values.slice();for(var end=a.length;end>1;end--){for(var i=0;i<end-1;i++){if(a[i]>a[i+1]){var v=a[i];a[i]=a[i+1];a[i+1]=v;}}}return a;}
  function edgeKey(a,b){return a<b?a+b:b+a;}
  function dijkstra(start,edges) {
    var dist={},prev={},settled=[];(lesson.data.nodes||[]).forEach(function(v){dist[v]=Infinity;prev[v]=null;});dist[start]=0;
    while(settled.length<(lesson.data.nodes||[]).length){var u=null,best=Infinity;Object.keys(dist).forEach(function(v){if(settled.indexOf(v)<0&&dist[v]<best){u=v;best=dist[v];}});if(u===null)break;settled.push(u);edges.forEach(function(e){var v=e[0]===u?e[1]:e[1]===u?e[0]:null;if(!v||settled.indexOf(v)>=0)return;var candidate=dist[u]+e[2];if(candidate<dist[v]){dist[v]=candidate;prev[v]=u;}});}
    return {dist:dist,prev:prev,settled:settled};
  }
  function reconstruct(start,end,prev){var out=[],v=end;while(v){out.unshift(v);if(v===start)return out;v=prev[v];}return [];}
  function graphState(r,selected,path,edges){return {distances:Object.keys(r.dist).reduce(function(o,k){o[k]=Number.isFinite(r.dist[k])?r.dist[k]:null;return o;},{}),settled:r.settled,selected:selected,routeEdges:edges,relaxed:[],note:path.length?'最短路径：'+path.join(' → '):'该终点不可达。'};}
  function gradient(x,alpha,count){var pts=[{x:x,y:x*x,direction:x>=0?'向左':'向右'}];for(var i=0;i<count;i++){var next=x-alpha*2*x;x=next;pts.push({x:x,y:x*x,direction:x>=0?'向左':'向右'});}return pts;}
  function safeDiv(a,b){return b===0?null:a/b;}
  function pct(v){return v==null?'暂无可计算值':(Math.round(v*1000)/10)+'%';}
  function metricCounts(threshold){var m={tp:0,fp:0,fn:0,tn:0};lesson.data.records.forEach(function(r){var predicted=r.score>=threshold;if(r.truth==='spam'&&predicted)m.tp++;else if(r.truth==='normal'&&predicted)m.fp++;else if(r.truth==='spam')m.fn++;else m.tn++;});return m;}
  function renderStart() {
    var first=lesson.steps[0];stageNode.innerHTML=render(first.state);captionNode.textContent=first.text;
    currentNode.textContent='准备观看 · '+lesson.gradeRange+' · '+lesson.stageName;
    statusNode.textContent='尚未开始；点击一次开始播放';
  }
  function metricPct(value){return value==null?'暂无可计算值':(Math.round(value*1000)/10)+'%';}
  window.addEventListener('resize',function(){if(practiceOpen){showPractice();}else if(lastState){stageNode.innerHTML=render(lastState);fitEmbeddedVisual();}});
  beginButton.addEventListener('click',function(){if(!embedded&&mode!=='playing')startFrom(0);});
  pauseButton.addEventListener('click',function(){if(mode==='paused')resumePlayback();else pausePlayback();});
  replayButton.addEventListener('click',function(){if(!embedded)startFrom(index);});
  restartButton.addEventListener('click',function(){if(!embedded){document.body.classList.remove('is-paused');startFrom(0);}});
  practiceButton.addEventListener('click',openPractice);
  byId('again').addEventListener('click',function(){document.body.classList.remove('is-paused');startFrom(0);});
  byId('try-after').addEventListener('click',openPractice);
  byId('rate').addEventListener('change',function(){rateValue=Number(this.value)||1;byId('settings-note').textContent='语速从下一段开始生效；静音阅读时长也会同步调整。';});
  byId('mute').addEventListener('change',function(){if(this.checked&&(mode==='playing'||mode==='reading')){generation++;stopSpeech();silentStep(generation,'静音播放：按字幕阅读时间自动继续');}});
  document.addEventListener('visibilitychange',function(){if(document.hidden){pausePlayback();var activeSvg=stageNode.querySelector('svg');if(activeSvg&&activeSvg.pauseAnimations)activeSvg.pauseAnimations();}});
  window.addEventListener('pagehide',pausePlayback);
  window.addEventListener('beforeunload',function(){generation++;clearTimer();stopSpeech();});
  renderStart();
  beginButton.disabled=Boolean(window.K12);
  if(window.K12)statusNode.textContent='正在等待霜铃平台初始化';

  async function setupHost() {
    try {
      hostContext=await window.K12.ready();
      hostReady=true;restorePractice(hostContext.gameState);
      if(window.K12.workspace&&window.K12.workspace.onSession)window.K12.workspace.onSession(function(s){
        var state=s.game_state;
        if(state&&state.state_version===1&&state.content_key==='autoplay-'+lesson.key&&state.practice&&Object.keys(practice).every(function(k){return JSON.stringify(state.practice[k])===JSON.stringify(practice[k]);}))saveNotice.textContent='实验已保存到账号';
      });
      var restoredIndex=lesson.steps.findIndex(function(_,i){return 'scene-'+String(i+1).padStart(2,'0')===hostContext.currentScene;});
      index=Math.max(0,restoredIndex);mode='host';void renderStep(lesson.steps[index]);
      if(window.K12.narration&&window.K12.narration.onState){window.K12.narration.onState(function(s){if(s.subtitle)captionNode.textContent=s.subtitle;statusNode.textContent=s.status==='speaking'?'平台正在朗读':s.status==='paused'?'平台朗读已暂停':s.status==='unavailable'?'没有可用声音，保留字幕':'平台讲解';});}
      if(!window.K12.workspace||!window.K12.workspace.register)return;
      var playback=lesson.steps.map(function(step,i){var id='scene-'+String(i+1).padStart(2,'0');return{scene_id:id,prompt_id:id+'-read'};});
      var receipt=await window.K12.workspace.register(['scene','pause','demonstrate'],async function(command){
        if(command.command==='scene'){
          var target=lesson.steps.findIndex(function(_,i){return 'scene-'+String(i+1).padStart(2,'0')===command.scene_id;});
          if(target<0)throw new Error('场景不存在');
          await window.K12.scene.enter(command.scene_id);
          document.body.classList.remove('is-practicing');byId('practice-panel').hidden=true;practiceOpen=false;
          index=target;mode='host';await renderStep(lesson.steps[index]);
        } else if(command.command==='pause'){
          generation++;clearTimer();stopSpeech();mode='host-paused';document.body.classList.add('is-paused');var activeSvg=stageNode.querySelector('svg');if(activeSvg&&activeSvg.pauseAnimations)activeSvg.pauseAnimations();
        } else if(command.command==='demonstrate'){
          if(command.prompt_id===null){document.body.classList.remove('is-paused');document.body.classList.add('is-practicing');mode='manual';practiceOpen=true;byId('practice-panel').hidden=false;practiceControls();showPractice();captionNode.textContent='手动实践已恢复；自动演示没有覆盖已保留的操作。';return;}
          var i=lesson.steps.findIndex(function(_,k){return 'scene-'+String(k+1).padStart(2,'0')+'-read'===command.prompt_id;});
          if(i<0||i!==index)throw new Error('讲解与当前场景不匹配');
          document.body.classList.remove('is-practicing');byId('practice-panel').hidden=true;practiceOpen=false;mode='host';await renderStep(lesson.steps[i]);
        }
      },{playback_steps:playback});
      if(receipt&&receipt.embedded===true){embedded=true;document.body.classList.add('embedded');fitEmbeddedVisual();statusNode.textContent='由霜铃平台接管场景和讲解';}
    } catch(_){
      hostReady=false;
      // Unsupported or older hosts keep the complete independent player visible.
    } finally {
      if(!embedded)beginButton.disabled=false;
    }
  }
  function practiceState(){
    if(lesson.kind==='input-process-output')return{stage:'output',input:practice.input,output:practice.input==='按键 A'?'圆灯亮':'三角灯亮',rule:lesson.data.rules[practice.input]};
    if(lesson.kind==='sorting-by-rule')return{rule:practice.rule,groups:grouping(lesson.data.items,practice.rule),note:'手动选择分类规则。'};
    if(lesson.kind==='robot-instructions')return simulateRobot(practice.route==='correct'?lesson.data.correct:lesson.data.wrong,lesson.data.walls,lesson.data.goal);
    if(lesson.kind==='pixels-build-picture')return{matrix:lesson.data.matrix,coarse:lesson.data.coarse,filled:16,note:practice.size+'×'+practice.size+' 网格使用同一图案。'};
    if(lesson.kind==='cards-bubble-sort')return{array:practice.operated?bubbleSortValues(practice.values):practice.values,left:null,right:null,note:practice.operated?'按相邻比较与交换得到结果。':'手动输入的数据。'};
    if(lesson.kind==='message-packets'){var order=(practice.order||'1,2,3').split(',');return{packets:order.map(function(id,i){var route=lesson.data.paths[id]||['S','A','C','T'];return{id:id,chunk:lesson.data.chunks[Number(id)-1],status:'arrived',order:i,path:route};}),note:'手动选择传输顺序：'+order.join('、')+'。'};}
    if(lesson.kind==='linear-search'){var ix=lesson.data.array.indexOf(practice.target);return{array:lesson.data.array,target:practice.target,current:practice.operated&&ix>=0?ix:null,checked:practice.operated?Array.from({length:ix>=0?ix+1:lesson.data.array.length},function(_,i){return i;}):[],codeLine:practice.operated?(ix>=0?2:3):0,note:practice.operated?(ix>=0?'找到后立即停止。':'全部检查后停止，不越界。'):'手动输入目标。'};}
    if(lesson.kind==='stack-and-queue')return{focus:practice.kind,stack:practice.kind==='stack'?practice.items:[],queue:practice.kind==='queue'?practice.items:[],stackOut:practice.kind==='stack'?practice.removed:[],queueOut:practice.kind==='queue'?practice.removed:[],note:'手动练习状态。'};
    if(lesson.kind==='training-and-testing'){var t=lesson.data.tests[practice.testIndex],pred=nearest(t.xy,lesson.data.train);return{train:lesson.data.train,test:{xy:t.xy},nearest:pred,phase:'test',prediction:pred.label,truth:t.truth,correct:pred.label===t.truth,note:'手动选择测试点。'};}
    if(lesson.kind==='shortest-path'){var r=dijkstra(practice.start,lesson.data.edges),path=reconstruct(practice.start,practice.end,r.prev),es=[];for(var j=0;j<path.length-1;j++)es.push(edgeKey(path[j],path[j+1]));return Object.assign(graphState(r,practice.end,path,es),{path:path});}
    if(lesson.kind==='gradient-descent'){var pts=gradient(4,practice.alpha,6);return{points:pts,current:pts[pts.length-1],iteration:pts.length-1,note:'按所选学习步长计算。'};}
    if(lesson.kind==='classification-metrics')return{counts:metricCounts(practice.threshold),threshold:practice.threshold,currentId:'全部样例',note:'手动阈值计算。'};
    return lesson.steps[index].state;
  }
  if(window.K12&&typeof window.K12.ready==='function')setupHost();
})();
