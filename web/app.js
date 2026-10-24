'use strict';
const $ = (id) => document.getElementById(id);
const translations = {
  pt: {
    studio:'Estúdio',activity:'Atividade',docs:'Documentação',local:'Seu ambiente. Seu controle.',
    headline:'Construa seu próximo<br><em>marco.</em>',subtitle:'Do primeiro pull request à colaboração em equipe.<br>Configure, visualize e execute em um só lugar.',
    available:'FLUXOS DISPONÍVEIS',ready:'prontos para configurar',execution:'EXECUÇÃO',credentials:'CREDENCIAIS',serveronly:'Só no servidor <span>fora do navegador</span>',
    choose:'01 / Escolha um fluxo',choosehint:'Um objetivo. Um plano claro.',configure:'02 / Configure a execução',repository:'Repositório de destino',repohint:'Use um repositório seu, inicializado com README e reservado para exercícios.',
    iterations:'Iterações',counthelp:'Até 8 por plano.<br>Execução sequencial.',coauthor:'Coautoria',name:'Nome do coautor',email:'E-mail associado ao GitHub',consent:'O coautor participou do trabalho e concordou com a atribuição.',
    preview:'Gerar prévia do plano',plan:'PLANO DE EXECUÇÃO',waiting:'Aguardando configuração',before:'Antes de executar, visualize.',beforehelp:'Seu plano aparece aqui com cada ação que será realizada no repositório.',
    disclaimer:'A conclusão do fluxo não confirma a conquista de uma badge. O GitHub avalia e concede achievements separadamente.',activitytitle:'03 / Registro de atividade',export:'Exportar JSON ↓',cancel:'Parar execução',emptylog:'Nenhuma execução nesta sessão. Comece configurando um fluxo.',footer:'Feito para explorar. Construído para ser seu.',
    quickdraw:'Abra e encerre uma issue em sequência.',yolo:'Crie um PR e faça merge sem solicitar review.',shark:'Automatize ciclos de pull request e merge.',pair:'Crie e preserve commits com coautoria.',
    quicksteps:['Criar uma issue','Encerrar a issue imediatamente'],prsteps:['Criar branch e registrar exercício','Abrir um pull request','Fazer merge do pull request'],pairsteps:['Criar commit com trailer de coautoria','Abrir um pull request','Fazer merge preservando o commit com coautoria'],yolosteps:['Criar branch e registrar exercício','Abrir um pull request','Fazer merge sem solicitar review'],
    confirm:'Digite o repositório para confirmar',execute:'Executar plano',simulate:'Simular plano',planned:'Plano pronto',working:'Processando…',demohint:'Demonstração: nenhuma alteração no GitHub. Execute python forge.py com GITHUB_TOKEN para usar o modo real.',
    completed:'Fluxo concluído. Confira seu perfil no GitHub; as badges são avaliadas separadamente.',stopped:'Execução parada. Operações já concluídas permanecem no repositório.',noexport:'Execute um plano antes de exportar.',error:'Não foi possível concluir a solicitação.',stale:'Configuração alterada. Gere uma nova prévia.',
    statuses:{running:'em execução',completed:'concluído',failed:'falhou',cancelled:'cancelado'},
  },
  en: {
    studio:'Studio',activity:'Activity',docs:'Documentation',local:'Your environment. Your control.',
    headline:'Build your next<br><em>milestone.</em>',subtitle:'From your first pull request to team collaboration.<br>Configure, preview and execute in one place.',
    available:'AVAILABLE WORKFLOWS',ready:'ready to configure',execution:'EXECUTION',credentials:'CREDENTIALS',serveronly:'Server only <span>outside the browser</span>',
    choose:'01 / Choose a workflow',choosehint:'One goal. One clear plan.',configure:'02 / Configure your run',repository:'Target repository',repohint:'Use a repository you own, initialized with a README and reserved for exercises.',
    iterations:'Iterations',counthelp:'Up to 8 per plan.<br>Sequential execution.',coauthor:'Co-authorship',name:'Co-author name',email:'GitHub-associated email',consent:'The co-author participated in the work and agreed to attribution.',
    preview:'Preview execution plan',plan:'EXECUTION PLAN',waiting:'Waiting for configuration',before:'Preview before you execute.',beforehelp:'Your plan will appear here with every action to be performed in the repository.',
    disclaimer:'Completing a workflow does not confirm a badge. GitHub evaluates and awards achievements separately.',activitytitle:'03 / Activity log',export:'Export JSON ↓',cancel:'Stop execution',emptylog:'No runs in this session. Start by configuring a workflow.',footer:'Made to explore. Built to be yours.',
    quickdraw:'Open and close an issue in sequence.',yolo:'Create a PR and merge without requesting review.',shark:'Automate pull request and merge cycles.',pair:'Create and preserve co-authored commits.',
    quicksteps:['Create an issue','Close the issue immediately'],prsteps:['Create branch and journal entry','Open a pull request','Merge the pull request'],pairsteps:['Create a commit with a co-author trailer','Open a pull request','Merge preserving the co-authored commit'],yolosteps:['Create branch and journal entry','Open a pull request','Merge without requesting review'],
    confirm:'Type the repository to confirm',execute:'Execute plan',simulate:'Simulate plan',planned:'Plan ready',working:'Processing…',demohint:'Demo: no GitHub changes. Run python forge.py with GITHUB_TOKEN to enable live mode.',
    completed:'Workflow completed. Check your GitHub profile; badges are evaluated separately.',stopped:'Execution stopped. Already-completed operations remain in the repository.',noexport:'Execute a plan before exporting.',error:'The request could not be completed.',stale:'Configuration changed. Generate a new preview.',
    statuses:{running:'running',completed:'completed',failed:'failed',cancelled:'cancelled'},
  },
};
const workflows = [
  {id:'quickdraw',name:'Quickdraw',icon:'ϟ',description:'quickdraw',steps:'quicksteps',tag:'ISSUE LIFECYCLE'},
  {id:'yolo',name:'YOLO',icon:'↗',description:'yolo',steps:'yolosteps',tag:'PULL REQUEST / MERGE'},
  {id:'pull-shark',name:'Pull Shark',icon:'⑂',description:'shark',steps:'prsteps',tag:'SEQUENTIAL WORKFLOWS'},
  {id:'pair-extraordinaire',name:'Pair Extraordinaire',icon:'⋈',description:'pair',steps:'pairsteps',tag:'CO-AUTHORED COMMITS'},
];
let language = localStorage.getItem('forge-language') === 'en' ? 'en' : 'pt';
let selected = workflows[0], plan = null, run = null, csrf = '', staticDemo = false, isDemo = true, busy = false, demoCancel = false;
const t = (key) => translations[language][key];
function notice(message, error = false) { $('notice').textContent = message; $('notice').className = error ? 'error' : ''; $('notice').hidden = false; }
function translate() {
  document.documentElement.lang = language === 'pt' ? 'pt-BR' : 'en';
  document.querySelectorAll('[data-t]').forEach(el => { el.innerHTML = t(el.dataset.t); });
  $('language').textContent = language === 'pt' ? 'EN ↗' : 'PT ↗';
  renderCards();
  if (plan) renderPlan();
  if (run) renderRun();
}
function renderCards() {
  $('workflows').replaceChildren();
  for (const workflow of workflows) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'workflow' + (selected.id === workflow.id ? ' selected' : '');
    button.setAttribute('aria-pressed', String(selected.id === workflow.id));
    button.innerHTML = `<span class="select-dot"></span><span class="workflow-icon">${workflow.icon}</span><h3>${workflow.name}</h3><p>${t(workflow.description)}</p><small>${workflow.tag}</small>`;
    button.disabled = busy;
    button.onclick = () => {
      selected = workflow; invalidate(); renderCards();
      $('selected-name').textContent = workflow.name.toUpperCase();
      $('coauthor').hidden = workflow.id !== 'pair-extraordinaire';
      $('coauthor-name').required = $('coauthor-email').required = $('coauthor-confirmed').required = workflow.id === 'pair-extraordinaire';
      $('count').disabled = ['quickdraw','yolo'].includes(workflow.id);
      if ($('count').disabled) $('count').value = '1';
    };
    $('workflows').append(button);
  }
}
function invalidate() {
  if (!plan) return;
  plan = null;
  $('plan-content').replaceChildren();
  const message = document.createElement('p'); message.className = 'plan-summary'; message.textContent = t('stale'); $('plan-content').append(message);
  $('plan-state').textContent = t('waiting');
}
async function api(path, data) {
  const response = await fetch(path, {method:data ? 'POST' : 'GET', headers: data ? {'Content-Type':'application/json','X-Forge-CSRF':csrf} : {}, body:data ? JSON.stringify(data) : undefined});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || t('error'));
  return body;
}
function config() {
  return {repository:$('repository').value.trim(), mode:selected.id, count:Number($('count').value), coauthor_name:$('coauthor-name').value.trim(),coauthor_email:$('coauthor-email').value.trim(),coauthor_confirmed:$('coauthor-confirmed').checked};
}
function renderPlan() {
  const container = $('plan-content'); container.replaceChildren();
  const summary = document.createElement('p'); summary.className = 'plan-summary'; summary.textContent = `${plan.demo ? 'DEMO' : 'LIVE'} / ${plan.repository} / ×${plan.count}`;
  const list = document.createElement('ol'); list.className = 'plan-steps';
  for (const step of t(selected.steps)) { const li = document.createElement('li'); li.textContent = step; list.append(li); }
  const box = document.createElement('div'); box.className = 'execute-box';
  if (plan.used) {
    const status = document.createElement('p'); status.className = 'plan-summary'; status.textContent = t('statuses')[run?.status] || t('working');
    box.append(status); container.append(summary,list,box); $('plan-state').textContent = status.textContent; return;
  }
  const label = document.createElement('label'); label.htmlFor = 'confirmation'; label.textContent = t('confirm');
  const input = document.createElement('input'); input.id = 'confirmation'; input.placeholder = plan.repository; input.autocomplete = 'off';
  const button = document.createElement('button'); button.className = 'primary'; button.textContent = t(plan.demo ? 'simulate' : 'execute') + ' ↗'; button.disabled = true;
  input.oninput = () => {button.disabled = input.value !== plan.repository || busy;};
  button.onclick = () => execute(input.value);
  box.append(label,input,button); container.append(summary,list,box); $('plan-state').textContent = t('planned');
}
function renderRun() {
  $('events').replaceChildren();
  for (const event of run.events) {
    const row = document.createElement('p'), time = document.createElement('time'), message = document.createElement('span');
    time.textContent = new Date(event.time).toLocaleTimeString(language === 'pt' ? 'pt-BR' : 'en-GB');
    message.textContent = event.messageKey ? t(event.messageKey) : Number.isInteger(event.stepIndex) ? '[DEMO] ' + t(workflows.find(w => w.id === run.mode).steps)[event.stepIndex] : event.message;
    row.append(time,message);
    if (event.url && /^https:\/\/github\.com\//.test(event.url)) { const link = document.createElement('a'); link.href = event.url; link.textContent = 'GitHub ↗'; link.target = '_blank'; link.rel = 'noreferrer'; row.append(link); }
    $('events').append(row);
  }
  $('run-state').textContent = `forge / ${run.demo ? 'demo / ' : ''}${t('statuses')[run.status] || run.status}`;
  $('progress-bar').style.width = `${(run.completed / run.total) * 100}%`;
  $('cancel').hidden = run.status !== 'running';
  $('events').scrollTop = $('events').scrollHeight;
}
function setBusy(value) { busy = value; $('preview-button').disabled = value; $('plan-form').querySelectorAll('input').forEach(el => { el.disabled = value; }); if (!value) $('count').disabled = ['quickdraw','yolo'].includes(selected.id); renderCards(); }
$('plan-form').addEventListener('input', invalidate);
$('plan-form').onsubmit = async (event) => {
  event.preventDefault(); $('notice').hidden = true;
  if (busy) return;
  setBusy(true);
  try {
    const data = config();
    if (!Number.isInteger(data.count) || data.count < 1 || data.count > 8) throw new Error('1–8 iterations');
    plan = staticDemo ? {...data, id:`demo-${Date.now()}-${Math.random().toString(36).slice(2,10)}`, demo:true} : await api('/api/plan',data);
    renderPlan();
  } catch (error) { notice(error.message, true); }
  finally { setBusy(false); }
};
async function execute(confirmation) {
  if (!plan || plan.used || busy) return;
  const activePlan = plan; setBusy(true); $('notice').hidden = true;
  $('plan-content').querySelectorAll('button,input').forEach(el => {el.disabled = true;});
  try {
    if (staticDemo) {
      demoCancel = false;
      run = {id:activePlan.id,repository:activePlan.repository,mode:activePlan.mode,demo:true,status:'running',events:[],completed:0,total:activePlan.count};
      for (let i=0;i<activePlan.count && !demoCancel;i++) {
        for (const [stepIndex,step] of t(selected.steps).entries()) {
          if (demoCancel) break;
          run.events.push({time:new Date().toISOString(),message:'[DEMO] ' + step,stepIndex}); renderRun();
          await new Promise(resolve => setTimeout(resolve,400));
        }
        if (!demoCancel) run.completed++;
      }
      run.status = demoCancel ? 'cancelled' : 'completed';
      run.events.push({time:new Date().toISOString(),message:t(demoCancel ? 'stopped' : 'completed'),messageKey:demoCancel ? 'stopped' : 'completed'}); renderRun();
    } else {
      run = await api('/api/execute',{plan_id:activePlan.id,confirmation}); renderRun();
      while (run.status === 'running') {
        await new Promise(resolve => setTimeout(resolve,1000));
        run = await api('/api/runs/' + run.id); renderRun();
      }
    }
  } catch (error) {
    notice(error.message, true);
    if (run?.status === 'running') { $('cancel').hidden = false; notice(error.message + ' / Run ID: ' + run.id, true); }
  } finally { activePlan.used = true; plan = activePlan; renderPlan(); setBusy(false); }
}
$('cancel').onclick = async () => { try { if (staticDemo) demoCancel = true; else await api('/api/cancel',{run_id:run.id}); } catch(error) {notice(error.message,true);} };
$('export').onclick = () => { if (!run) return notice(t('noexport')); const url=URL.createObjectURL(new Blob([JSON.stringify(run,null,2)],{type:'application/json'})); const a=document.createElement('a'); a.href=url; a.download=`forge-${run.id}.json`; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); };
$('language').onclick = () => {language = language === 'pt' ? 'en' : 'pt'; localStorage.setItem('forge-language',language);translate();};
async function init() {
  translate(); $('count').disabled = true;
  try { const status = await api('/api/status'); csrf=status.csrf;isDemo=status.demo; }
  catch {staticDemo=true;isDemo=true;}
  $('mode-label').textContent = isDemo ? 'DEMO' : 'LIVE';
  if (isDemo) notice(t('demohint'));
}
init();
