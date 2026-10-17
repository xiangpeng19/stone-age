"use strict";
const $ = id => document.getElementById(id);
const ui = {online:false, pending:false, socket:null, nextId:1, requests:new Map(), map:null, position:null, moves:0};
const errors = {demo_busy:"另一个标签页正在控制测试角色，请先在那里断开。",busy:"上一个动作仍在处理。",request_pending:"这个动作正在处理中。",rate_limited:"移动太快，请稍等片刻。",not_connected:"请先进入演示。",invalid_request:"输入未被接受，角色状态未改变。",native_connection_lost:"与服务端的连接已断开，请重新进入。",native_timeout:"服务端暂未响应，请重新进入。",save_timeout:"尚未确认存档，请稍后重试。",unsupported_map:"演示只支持当前测试地图。"};

function notice(text, error=false) { $("notice").textContent=text; $("notice").classList.toggle("error",error); }
function event(text) { const li=document.createElement("li"); li.textContent=text; $("events").prepend(li); while($("events").children.length>7)$("events").lastChild.remove(); }
function controls() {
  $("enter").disabled=ui.pending||ui.online;
  $("enter").textContent=ui.online?"已进入测试营地":"进入演示 ↗";
  for(const button of document.querySelectorAll(".direction, #save, #disconnect, #logout"))button.disabled=ui.pending||!ui.online;
  $("connection").classList.toggle("online",ui.online);
  $("connection").lastChild.textContent=ui.online?"已连接服务端":"未连接";
  $("busy").hidden=!ui.pending;
}
function position(value) {
  if(!value)return;
  ui.position=value;
  $("coordinates").textContent=`${value.x}, ${value.y}`;
  $("map-id").textContent=`MAP ${value.floor}`;
  $("authority").textContent="位置已由服务端确认";
  draw();
}
function saved(value,confirmed=false) {
  if(!value)return;
  const p=value.position;
  $("save-status").textContent=`${confirmed?"已确认存档":"最近存档"} · 地图 ${p.floor} · ${p.x}, ${p.y}`;
  $("save-status").classList.toggle("confirmed",confirmed);
}
function draw() {
  const canvas=$("map"),ctx=canvas.getContext("2d");
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if(!ui.map)return;
  const m=ui.map,tile=16;
  canvas.width=m.width*tile;canvas.height=m.height*tile;
  const shades=["#d8dfbc","#d0d9b4","#dce2c5","#c6d1aa","#e4e5ce","#cfd8ba","#d8dfc3"];
  for(let y=0;y<m.height;y++)for(let x=0;x<m.width;x++){
    const i=y*m.width+x,px=x*tile,py=y*tile;
    ctx.fillStyle=shades[m.tiles[i]%shades.length];ctx.fillRect(px,py,tile,tile);
    ctx.strokeStyle="#ffffff13";ctx.strokeRect(px+.5,py+.5,tile,tile);
    if(m.objects[i]){
      ctx.fillStyle="#728164";ctx.fillRect(px+2,py+2,tile-4,tile-4);
      ctx.fillStyle="#8c9976";ctx.fillRect(px+3,py+2,tile-6,3);
    }
    if(m.events[i]){ctx.fillStyle="#b99558";ctx.beginPath();ctx.arc(px+8,py+8,2,0,Math.PI*2);ctx.fill();}
  }
  if(ui.position){
    const x=(ui.position.x-m.bounds[0]+.5)*tile,y=(ui.position.y-m.bounds[1]+.5)*tile;
    ctx.globalAlpha=ui.online?1:.45;
    ctx.fillStyle="#2b493b33";ctx.beginPath();ctx.ellipse(x,y+6,9,4,0,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle="#f9f5d8";ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,10,0,Math.PI*2);ctx.stroke();
    ctx.fillStyle="#527e95";ctx.fillRect(x-5,y-1,10,11);ctx.fillStyle="#e3bd8c";ctx.fillRect(x-4,y-8,8,9);
    ctx.fillStyle="#52634e";ctx.fillRect(x-5,y-10,10,4);ctx.fillStyle="#35576b";ctx.fillRect(x-5,y+8,4,4);ctx.fillRect(x+1,y+8,4,4);
    ctx.globalAlpha=1;
  }
}
async function connect() {
  if(ui.socket&&ui.socket.readyState===WebSocket.OPEN)return;
  const socket=new WebSocket(`ws://${location.host}/ws`);ui.socket=socket;
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error("无法连接本机网关。")),7000);
    socket.addEventListener("open",()=>{clearTimeout(timer);resolve();},{once:true});
    socket.addEventListener("error",()=>{clearTimeout(timer);reject(new Error("无法连接本机网关，请检查 SSH 隧道。"));},{once:true});
    socket.addEventListener("message",message=>{
      let data;try{data=JSON.parse(message.data);}catch{return;}
      const pending=ui.requests.get(data.id);
      if(pending){ui.requests.delete(data.id);clearTimeout(pending.timer);if(!data.ok&&data.online===false)ui.online=false;data.ok?pending.resolve(data):pending.reject(new Error(errors[data.error]||"操作未完成，请重新进入演示。"));}
    });
    socket.addEventListener("close",()=>{
      if(ui.socket!==socket)return;
      ui.online=false;
      for(const request of ui.requests.values()){clearTimeout(request.timer);request.reject(new Error("连接已断开，请重新进入演示。"));}
      ui.requests.clear();controls();draw();notice("连接已断开，可重新进入恢复保存位置。",true);
    });
  });
}
function rpc(action, extra={}) {
  const id=ui.nextId++;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{ui.requests.delete(id);reject(new Error("等待服务端超时，请重新进入。"));ui.socket?.close();},40000);
    ui.requests.set(id,{resolve,reject,timer});
    ui.socket.send(JSON.stringify({id,action,...extra}));
  });
}
async function act(action,extra={}) {
  if(ui.pending)return;
  ui.pending=true;controls();
  $("busy-label").textContent=action==="save"?"等待原生自动存档写盘…":action==="enter"?"正在准备测试角色与地图…":"正在等待服务端确认…";
  try{
    await connect();const result=await rpc(action,extra);
    if(typeof result.online==="boolean")ui.online=result.online;
    if(result.map){ui.map=result.map;$("map-name").textContent=result.map.name||"测试地图";$("welcome").hidden=true;}
    if(result.stats){$("level").textContent=result.stats.level;$("gold").textContent=result.stats.gold.toLocaleString("zh-CN");}
    position(result.position);saved(result.saved,Boolean(result.save_confirmed||result.normal_logout));
    if(action==="enter"){notice("已进入营地，试着走一小步。");event(result.created?"测试角色已创建并进入地图。":"已选择测试角色，恢复服务端保存位置。");$("map").parentElement.focus({preventScroll:true});}
    if(action==="move"){ui.moves++;notice(result.blocked?"前方未能通行，服务端坐标保持原位。":`移动已确认 · ${result.position.x}, ${result.position.y}`);event(result.blocked?"这一步被服务端阻挡。":`服务器确认位置 ${result.position.x}, ${result.position.y}。`);}
    if(action==="save"){notice("已确认当前位置写入原生存档。");event("在线自动存档已核实，可断开后重新进入验证。");}
    if(action==="disconnect"){notice("已断开，可重新进入恢复保存位置。");event("已模拟断线，未发送正常退出指令。");}
    if(action==="logout"){notice("正常退出完成，已按游戏规则保存出生点。");event("正常退出已确认，与断线恢复分开处理。");if(result.saved)position({...ui.position,...result.saved.position});}
    draw();
  }catch(error){notice(error.message,true);event(error.message);if(!ui.socket||ui.socket.readyState!==WebSocket.OPEN)ui.online=false;}
  finally{ui.pending=false;controls();}
}
$("enter").addEventListener("click",()=>act("enter"));
$("save").addEventListener("click",()=>act("save"));
$("disconnect").addEventListener("click",()=>act("disconnect"));
$("logout").addEventListener("click",()=>act("logout"));
for(const button of document.querySelectorAll(".direction"))button.addEventListener("click",()=>act("move",{direction:button.dataset.direction}));
const keys={ArrowUp:"north",w:"north",W:"north",ArrowRight:"east",d:"east",D:"east",ArrowDown:"south",s:"south",S:"south",ArrowLeft:"west",a:"west",A:"west"};
document.addEventListener("keydown",event=>{const direction=keys[event.key];if(direction&&ui.online){event.preventDefault();if(!event.repeat&&!ui.pending)act("move",{direction});}});
controls();draw();
