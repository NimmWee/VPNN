'use strict';
let csrf = '';
let state = null;
const byId = id => document.getElementById(id);
function notice(message) { const el=byId('notice');el.textContent=message;el.hidden=false;setTimeout(()=>{el.hidden=true;},7000); }
async function api(path,method='GET',body) {
  const response=await fetch('/api/admin/'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) {if(response.status===401)showLogin();throw new Error(data.error||'Ошибка запроса');}
  return data;
}
function showLogin(){byId('login').hidden=false;byId('panel').hidden=true;byId('logout').hidden=true;csrf='';state=null;byId('inviteText').value='';byId('invite').hidden=true;byId('adminToken').value='';byId('groups').replaceChildren();byId('devices').replaceChildren();byId('publicKey').textContent='';}
function groupRow(group) {
  const row=byId('groupTemplate').content.firstElementChild.cloneNode(true);
  for(const field of ['id','name'])row.querySelector('[data-field='+field+']').value=group[field];
  row.querySelector('[data-field=calls]').value=(group.calls||[]).join('\n');
  row.querySelector('[data-field=profiles]').value=JSON.stringify(group.profiles||{},null,2);
  row.querySelector('[data-action=remove]').addEventListener('click',()=>row.remove());
  byId('groups').append(row);
}
function render() {
  byId('login').hidden=true;byId('panel').hidden=false;byId('logout').hidden=false;
  byId('version').textContent='Версия настроек '+state.version;
  const network=state.networkStatus;
  byId('networkStatus').textContent=network?(network.healthy?(network.appliedVersion<state.version?'Ожидаем применения версии '+state.version+'. Последняя подтверждённая: '+network.appliedVersion:'Сервер применил версию '+network.appliedVersion+' · DNS: '+network.dnsDevices+' · VK: '+network.vkDevices):'Нет свежего подтверждения сетевого доступа. Проверь службу синхронизации сервера.'):'Синхронизация сетевого доступа не настроена';
  byId('publicKey').textContent=state.publicKey;
  byId('groups').replaceChildren();state.groups.forEach(groupRow);
  byId('deviceGroup').replaceChildren(...state.groups.map(g=>new Option(g.name,g.id)));
  byId('devices').replaceChildren();
  for(const d of state.devices.sort((a,b)=>a.name.localeCompare(b.name))) {
    const row=document.createElement('article');row.className='device';
    const title=document.createElement('strong');title.textContent=d.name+(d.enabled?'':' · отозван');row.append(title);
    for(const text of ['Группа: '+d.group,'IP WireGuard: '+d.wgIPv4,'UUID: '+d.uuid,'Последний запрос: '+(d.lastSeen?new Date(d.lastSeen*1000).toLocaleString():'ещё не подключалось'),'Подтверждённая версия: '+(d.ackVersion||'—')]){const p=document.createElement('p');p.textContent=text;row.append(p);}
    if(d.enabled){const button=document.createElement('button');button.className='danger';button.textContent='Отозвать доступ';button.addEventListener('click',async()=>{if(!confirm('Закрыть доступ для «'+d.name+'»? Действующая сессия отключится после применения изменений сервером.'))return;try{await api('devices/'+encodeURIComponent(d.id)+'/revoke','POST',{});await refresh();notice('Отзыв опубликован. Дождись подтверждения версии сервером.');}catch(e){notice(e.message);}});row.append(button);}
    byId('devices').append(row);
  }
}
async function refresh(){state=await api('state');csrf=state.csrf;render();}
byId('loginForm').addEventListener('submit',async event=>{event.preventDefault();try{const login=await api('login','POST',{token:byId('adminToken').value});byId('adminToken').value='';csrf=login.csrf;await refresh();}catch(e){notice(e.message);}});
byId('logout').addEventListener('click',async()=>{try{await api('logout','POST',{});showLogin();}catch(e){notice(e.message);}});
byId('refresh').addEventListener('click',()=>refresh().catch(e=>notice(e.message)));
byId('addGroup').addEventListener('click',()=>groupRow({id:'group-'+(Date.now()%100000),name:'Новая группа',calls:[],profiles:{direct:{proxies:[{name:'VPNN',type:'vless',server:'REPLACE_WITH_SERVER',port:443,uuid:'${device.uuid}',tls:true,network:'tcp'}],'proxy-groups':[{name:'VPNN mode',type:'select',proxies:['VPNN']}],rules:['MATCH,VPNN mode']}}}));
byId('saveGroups').addEventListener('click',async()=>{try{const groups=Array.from(byId('groups').children).map(row=>({id:row.querySelector('[data-field=id]').value.trim(),name:row.querySelector('[data-field=name]').value.trim(),calls:row.querySelector('[data-field=calls]').value.split('\n').map(x=>x.trim()).filter(Boolean),profiles:JSON.parse(row.querySelector('[data-field=profiles]').value)}));await api('groups','PUT',groups);await refresh();notice('Новая версия опубликована');}catch(e){notice(e.message);}});
byId('deviceForm').addEventListener('submit',async event=>{event.preventDefault();try{const invite=await api('devices','POST',{name:byId('deviceName').value,group:byId('deviceGroup').value});const url=new URL('vpnn://enroll');url.searchParams.set('url',location.origin);url.searchParams.set('token',invite.token);url.searchParams.set('key',invite.publicKey);url.searchParams.set('device',invite.deviceId);byId('inviteText').value=url.toString();byId('invite').hidden=false;await refresh();notice('Приглашение создано');}catch(e){notice(e.message);}});
byId('copyInvite').addEventListener('click',()=>navigator.clipboard.writeText(byId('inviteText').value).then(()=>notice('Приглашение скопировано')).catch(()=>notice('Выдели текст приглашения и скопируй вручную')));
byId('downloadBootstrap').addEventListener('click',async()=>{try{
  const invitation=new URL(byId('inviteText').value);
  const response=await fetch('/api/device/bootstrap',{headers:{Authorization:'Bearer '+invitation.searchParams.get('token')}});
  if(!response.ok)throw new Error('Не удалось подготовить файл первого подключения');
  const bundle=await response.json();
  const address=URL.createObjectURL(new Blob([JSON.stringify(bundle)],{type:'application/json'}));
  const link=document.createElement('a');link.href=address;link.download='VPNN-bootstrap.json';link.click();setTimeout(()=>URL.revokeObjectURL(address),1000);
  notice('Файл подготовлен. Передай его только владельцу устройства.');
}catch(error){notice(error.message);}});
refresh().catch(()=>{});
