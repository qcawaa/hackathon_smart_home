import { useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Descriptions, Divider, Drawer, Form, Input, InputNumber, Layout, Menu, Modal, notification, Row, Select, Slider, Space, Switch, Tag, Typography } from 'antd';
import { ApiOutlined, AppstoreOutlined, BulbOutlined, CoffeeOutlined, HomeOutlined, MoonOutlined, PicCenterOutlined, ControlOutlined, DeleteOutlined, DeploymentUnitOutlined, InfoCircleOutlined, PlusOutlined, QuestionCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Background, Controls, MarkerType, ReactFlow, addEdge, useEdgesState, useNodesState, type Connection, type Edge, type Node } from '@xyflow/react';
import { request, wsUrl } from './api';
import LivePanel from './LivePanel';

const { Sider, Header, Content } = Layout;
const { Title, Text } = Typography;
type Signal = { name: string; title: string; description?: string; control: string; management: string; kind: string; group: string; section?: string; event_title?: string; event_on?: string; event_off?: string; action_title?: string; action_on?: string; action_off?: string; measure?: string; min?: number; max?: number; layout?: Record<string, string> };
type Device = { id: string; title: string; model: string; type?: string; preset_title?: string; icon?: string; user_created?: boolean; deletable?: boolean; state: Record<string, any>; declaration: Signal[]; source: string };
type DevicePreset = { type: string; title: string; icon: string; description: string; features: Record<string,string[]>; declaration: Signal[] };
type Scenario = { id: string; title: string; enabled: boolean; execution_mode: string; ujin_id?: string; trigger: any; condition?: any; conditions?: any[]; action?: any; actions?: any[]; graph?: { nodes: Node[]; edges: Edge[] } };
type ScenarioActionNotice = {id:string;status:'success'|'warning'|'error';message:string};
const shownScenarioActions = new Set<string>();
function showScenarioAction(notice:ScenarioActionNotice) {
  if(shownScenarioActions.has(notice.id))return;
  shownScenarioActions.add(notice.id);
  if(shownScenarioActions.size>300)shownScenarioActions.delete(shownScenarioActions.values().next().value!);
  notification[notice.status]({message:notice.message,placement:'bottomRight',duration:4,style:{width:320,padding:'12px 16px'}});
}
type SignalContext = 'trigger' | 'condition' | 'action';
type Rule = { device_id: string; signal: string; operator: string; value: any };
const quickScenarios = [
  {id:'quick_home',title:'Я дома',description:'Включить все светильники и чайники.'},
  {id:'quick_good_night',title:'Спокойной ночи!',description:'Выключить все светильники и закрыть шторы.'},
];
const groups: Record<string, string> = { property: 'Свойства', capability: 'Возможности', setting: 'Настройки' };

const operatorLabels: Record<string,string> = { '==':'Равно', eq:'Равно', '!=':'Не равно', ne:'Не равно', '>':'Больше', gt:'Больше', '<':'Меньше', lt:'Меньше', '>=':'Больше или равно', gte:'Больше или равно', '<=':'Меньше или равно', lte:'Меньше или равно' };

export function getAvailableSignals(device: Device | undefined, context: SignalContext): Signal[] {
  if (!device) return [];
  return device.declaration.filter(signal => {
    if (signal.name === 'fw' || signal.kind === 'system') return false;
    const commandLike = signal.control === 'push_time' || signal.control === 'button' || /_cmd$/i.test(signal.name);
    if (context === 'action') return ['rw','w'].includes(signal.management);
    return ['r','rw'].includes(signal.management) && (!commandLike || Boolean(signal.event_title));
  });
}

function getVisibleSignals(device: Device) {
  return device.declaration.filter(signal => signal.name !== 'fw' && signal.kind !== 'system');
}

function isBooleanSignal(signal: Signal) {
  if (signal.control === 'switch') return true;
  const keys = Object.keys(signal.layout || {}).map(Number).sort();
  return signal.control === 'list' && keys.length === 2 && keys[0] === 0 && keys[1] === 1;
}
function isEnumSignal(signal: Signal) { return Boolean(signal.layout && Object.keys(signal.layout).length) && !isBooleanSignal(signal); }
function isNumericSignal(signal: Signal) { return ['number','range','counter','graph'].includes(signal.control) || Boolean(signal.measure || signal.min !== undefined || signal.max !== undefined); }
function isCommandSignal(signal: Signal) { return ['push_time','button'].includes(signal.control) || /_cmd$/i.test(signal.name); }
export function getHumanOperator(operator: string) { return operatorLabels[operator] || 'Равно'; }
export function getSignalDisplayName(signal?: Signal) { return signal?.title || 'состояние'; }
function formatSignalValue(signal: Signal, value: any) {
  if (signal.control === 'switch') return Number(value) ? 'Вкл' : 'Выкл';
  const mapped = signal.layout?.[String(value)];
  if (mapped !== undefined) {
    if (/протеч/i.test(signal.title)) return Number(value) ? 'Обнаружена' : 'Не обнаружена';
    const normalized = String(mapped).trim();
    if (/^(вкл|включено|включён|on)$/i.test(normalized)) return 'Вкл';
    if (/^(выкл|выключено|выключен|off)$/i.test(normalized)) return 'Выкл';
    return normalized ? normalized[0].toLocaleUpperCase('ru-RU') + normalized.slice(1) : normalized;
  }
  if (value === null || value === undefined || value === '') return 'Нет данных';
  return `${value}${signal.measure ? ` ${signal.measure}` : ''}`;
}
function getPrimarySignal(device: Device) {
  const signals = getVisibleSignals(device);
  const preferred: Record<string, string> = {
    emul_leak_sensor: 'leak', emul_light: 'lamp', emul_thermostat: 'mode',
    emul_barrier: 'state', emul_counter: 'load_relay',
    emul_water_valve: 'opened', emul_kettle: 'on', emul_curtain: 'opened',
  };
  const typePreferred: Record<string,string> = {light:'lamp',leak:'leak',thermostat:'mode',barrier:'state',counter:'total',water_valve:'opened',kettle:'on',curtain:'opened'};
  const preferredSignal = signals.find(signal => signal.name === (typePreferred[device.type||''] || preferred[device.model]));
  if (preferredSignal) return preferredSignal;
  return signals.find(signal => signal.control === 'switch')
    || signals.find(signal => signal.layout && Object.keys(signal.layout).length)
    || signals.find(signal => signal.name !== 'battery' && signal.management !== 'w')
    || signals[0];
}
export function getHumanValue(signal: Signal, value: any) {
  if (signal.layout?.[String(value)] !== undefined || signal.control === 'switch') return formatSignalValue(signal,value);
  if (isBooleanSignal(signal)) {
    const positive = Number(value) === 1 || value === true;
    if (/протеч|вода|leak/i.test(`${signal.name} ${signal.title}`)) return positive ? 'Обнаружена' : 'Не обнаружена';
    if (/свет|ламп|light|lamp/i.test(`${signal.name} ${signal.title}`)) return positive ? 'Включён' : 'Выключен';
    return positive ? 'Да' : 'Нет';
  }
  return String(value ?? '');
}
function getDefaultRuleValue(signal: Signal) { return signal.layout?.['0'] !== undefined ? 0 : signal.min ?? 0; }
function getActionDefault(signal: Signal, device?: Device) {
  if (isCommandSignal(signal)) return 1;
  if (signal.control === 'combolist') return Math.min(...Object.keys(signal.layout||{}).map(Number).filter(value=>Number.isFinite(value)&&value>0));
  if (isBooleanSignal(signal)) return 1;
  if (isEnumSignal(signal)) return Number(Object.keys(signal.layout || {})[0] ?? 0);
  return device?.state?.[signal.name] ?? signal.min ?? 0;
}
function formatRulePhrase(rule: Rule, devices: Device[]) {
  const device = devices.find(item => item.id === rule.device_id);
  const signal = device?.declaration.find(item => item.name === rule.signal);
  if (!signal) return 'выбранное событие';
  const title = signal.title.toLocaleLowerCase('ru-RU');
  if (signal.event_title) {
    const event = Number(rule.value) ? (signal.event_on || signal.event_title) : (signal.event_off || signal.event_title);
    return `${device?.title.toLocaleLowerCase('ru-RU')}: ${event.toLocaleLowerCase('ru-RU')}`;
  }
  if (isBooleanSignal(signal)) {
    const value = getHumanValue(signal, rule.value).toLocaleLowerCase('ru-RU');
    if (/протеч|вода|leak/i.test(`${signal.name} ${signal.title}`)) return rule.value ? 'обнаружена протечка' : 'протечка не обнаружена';
    if (/свет|ламп|light|lamp/i.test(`${signal.name} ${signal.title}`)) return `свет ${value}`;
    return `${title}: ${value}`;
  }
  const value = `${getHumanValue(signal, rule.value)}${signal.measure ? ` ${signal.measure}` : ''}`;
  return `${title} станет ${getHumanOperator(rule.operator).toLocaleLowerCase('ru-RU')} ${value}`;
}
function formatActionPhrase(action: any, devices: Device[]) {
  const device = devices.find(item => item.id === action?.device_id);
  const signal = device?.declaration.find(item => item.name === action?.signal);
  if (!signal) return 'выберите действие';
  if (isCommandSignal(signal)) return `${(signal.action_title||signal.title).toLocaleLowerCase('ru-RU')} (${device?.title.toLocaleLowerCase('ru-RU')})`;
  if (isBooleanSignal(signal)) {
    if (signal.action_on || signal.action_off) { const label=(Number(action.value)?signal.action_on:signal.action_off)||signal.action_title||signal.title; return `${label.toLocaleLowerCase('ru-RU')} (${device?.title.toLocaleLowerCase('ru-RU')})`; }
    const verb = Number(action.value) ? 'включить' : 'выключить';
    const subject = /свет|ламп|light|lamp/i.test(`${signal.name} ${signal.title}`) ? 'свет' : signal.title.toLocaleLowerCase('ru-RU');
    return `${verb} ${subject}`;
  }
  const value = `${getHumanValue(signal, action.value)}${signal.measure ? ` ${signal.measure}` : ''}`;
  return `установить ${signal.title.toLocaleLowerCase('ru-RU')} на ${value}`;
}
export function formatScenarioHumanReadable(trigger: Rule, condition: Rule | null, action: any, devices: Device[]) {
  const when = formatRulePhrase(trigger, devices);
  const ifPart = condition ? `, если ${formatRulePhrase(condition, devices)}` : '';
  const then = formatActionPhrase(action, devices);
  return `Когда ${when}${ifPart}, тогда ${then}.`;
}

export default function App() {
  const [page, setPage] = useState('overview');
  const [devices, setDevices] = useState<Device[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<Device | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [live, setLive] = useState<any>({ configured: false, connected: false });
  const [builderOpen, setBuilderOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameDevice, setRenameDevice] = useState<Device | null>(null);
  const [renameTitle, setRenameTitle] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Device | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [liveOpen, setLiveOpen] = useState(false);
  const [scenarioEdit, setScenarioEdit] = useState<Scenario | null>(null);
  const [scenarioEditorOpen, setScenarioEditorOpen] = useState(false);
  const openScenarioEditor = (scenario: Scenario | null) => { setScenarioEdit(scenario); setScenarioEditorOpen(true); };
  const refresh = async () => {
    try { const [d,s,l] = await Promise.all([request<Device[]>('/devices'), request<Scenario[]>('/scenarios'), request<any>('/live/status')]); setDevices(d); setScenarios(s); setLive(l); } catch (e: any) { notification.error({ message: 'Backend недоступен', description: e.message }); }
  };
  useEffect(() => { refresh(); request<any[]>('/events').then(setLogs).catch(()=>{}); }, []);
  useEffect(() => {
    let socket: WebSocket | undefined; let retry: number;
    const connect = () => { socket = new WebSocket(wsUrl); socket.onmessage = (msg) => { const e = JSON.parse(msg.data); if (e.type === 'device_state') { setDevices(old => old.map(d => d.id === e.device_id ? { ...d, state: e.state } : d)); setSelected(old => old && old.id === e.device_id ? { ...old, state: e.state } : old); } if (e.type === 'scenario_action') showScenarioAction(e); if (e.type === 'integration_status') setLive(e.status); if (e.type === 'execution') setLogs(old => [e.item, ...old].slice(0,100)); }; socket.onclose = () => { retry = window.setTimeout(connect, 1800); }; };
    connect(); return () => { window.clearTimeout(retry); socket?.close(); };
  }, []);
  const detail = async (id: string) => { try { setSelected(await request<Device>(`/devices/${id}`)); setPage('devices'); } catch (e:any) { notification.error({ message: e.message }); } };
  const command = async (device: Device, signal: Signal, value: any) => { try { const result=await request<any>(`/devices/${device.id}/command/${signal.name}`, { method:'POST', body: JSON.stringify({value}) }); if(signal.name==='self_test'&&result.command_result) notification.success({message:'Проверка датчика завершена',description:result.command_result,duration:7}); else if(result.command_result) notification.info({message:'Результат команды',description:result.command_result,duration:7}); else notification.success({message:'Команда выполнена', description:`${signal.title}: ${formatSignalValue(signal,value)}`}); await refresh(); if(selected?.id===device.id) setSelected(await request<Device>(`/devices/${device.id}`)); } catch(e:any) { notification.error({message:'Не удалось изменить сигнал',description:e.message}); } };
  const removeDevice = (device: Device) => { setDeleteTarget(device); setDeleteError(''); };
  const confirmDeleteDevice = async () => {
    if (!deleteTarget || deleteBusy) return;
    const target=deleteTarget;
    setDeleteBusy(true); setDeleteError('');
    try {
      await request(`/devices/${encodeURIComponent(target.id)}`, { method:'DELETE' });
      setDevices(current=>current.filter(item=>item.id!==target.id));
      setSelected(current=>current?.id===target.id?null:current);
      setDeleteTarget(null); setPage('devices');
      notification.success({message:`«${target.title}» удалено`});
      await refresh();
    } catch(e:any) {
      setDeleteError(e?.message||'Сервер не подтвердил удаление. Обновите страницу и попробуйте ещё раз.');
    } finally { setDeleteBusy(false); }
  };
  const removeScenario = async (scenario: Scenario) => {
    await request(`/scenarios/${encodeURIComponent(scenario.id)}`, {method:'DELETE'});
    setScenarios(current=>current.filter(item=>item.id!==scenario.id));
    if(scenarioEdit?.id===scenario.id){setScenarioEdit(null);setScenarioEditorOpen(false);}
    notification.success({message:`Сценарий «${scenario.title}» удалён`});
  };
  const openScenariosForDelete = () => { setDeleteTarget(null); setDeleteError(''); setSelected(null); setPage('scenarios'); };
  const saveRename = async () => {
    if (!renameDevice || renameTitle.trim().length < 2) return;
    try { await request(`/devices/${renameDevice.id}`, {method:'PUT',body:JSON.stringify({title:renameTitle.trim()})}); setRenameOpen(false); setRenameDevice(null); await refresh(); if(selected?.id===renameDevice.id) setSelected(await request<Device>(`/devices/${renameDevice.id}`)); notification.success({message:'Название обновлено'}); }
    catch(e:any) { notification.error({message:'Не удалось изменить название',description:e.message}); }
  };
  const menu = [{key:'overview',icon:<AppstoreOutlined/>,label:'Главная'},{key:'devices',icon:<ControlOutlined/>,label:'Устройства'},{key:'scenarios',icon:<DeploymentUnitOutlined/>,label:'Сценарии'}];
  return <Layout className="app-shell"><Sider width={238} className="side"><div className="brand"><div><b>UJIN</b><span>SMART HOME</span></div></div><Menu mode="inline" selectedKeys={[page]} items={menu} onClick={({key})=>{setPage(key);setSelected(null);}}/></Sider><Layout><Header className="topbar"><div><Text className="crumb">ПРОСТРАНСТВО / </Text><Text strong>{menu.find(m=>m.key===page)?.label.toUpperCase() || 'УСТРОЙСТВО'}</Text></div><Space><Tag color="cyan" className="mode-tag">{live.running ? 'LIVE' : 'LOCAL'}</Tag><span className="live-dot"/><Text type="secondary">{devices.length} устройств</Text><Button size="small" onClick={()=>setLiveOpen(true)}>Ujin OS · {live.connected?'на связи':live.configured?'настроен':'настройка'}</Button></Space></Header><Content className="content">
    {page==='overview' && <Dashboard live={live} devices={devices} scenarios={scenarios} logs={logs} onOpen={detail} onCreate={()=>setBuilderOpen(true)} onDelete={removeDevice} onQuickComplete={refresh} />}
    {page==='devices' && <DevicesPage devices={devices} selected={selected} onOpen={detail} onBack={()=>setSelected(null)} onCommand={command} onSimulate={async(d,v)=>{const signal='leak';try{await request(`/devices/${d.id}/simulate`,{method:'POST',body:JSON.stringify({signal,value:v})});await refresh();if(selected)setSelected(await request<Device>(`/devices/${selected.id}`));}catch(e:any){notification.error({message:e.message});}}} onBuild={()=>setBuilderOpen(true)} onEditDevice={device=>{setRenameDevice(device);setRenameTitle(device.title);setRenameOpen(true);}} onDeleteDevice={removeDevice} />}
    {page==='scenarios' && <ScenarioPage scenarios={scenarios} devices={devices} logs={logs} onEdit={openScenarioEditor} onRefresh={refresh} onDelete={removeScenario} />}
  </Content></Layout>
  <DevicePresetFlow open={builderOpen} onClose={()=>setBuilderOpen(false)} onDone={async id=>{setBuilderOpen(false);await refresh();if(id)await detail(id);}}/>
  <Modal open={Boolean(deleteTarget)} title="Удалить устройство?" okText="Удалить" cancelText="Отмена" okButtonProps={{danger:true}} confirmLoading={deleteBusy} onCancel={()=>{if(!deleteBusy){setDeleteTarget(null);setDeleteError('');}}} onOk={confirmDeleteDevice}>
    {deleteTarget&&<Text>Устройство «{deleteTarget.title}» будет удалено из списка.</Text>}
    {deleteError&&<Alert style={{marginTop:14}} type="warning" showIcon message="Удаление не выполнено" description={<Space direction="vertical" size={8}><span>{deleteError}</span>{/используется в сценарии/i.test(deleteError)&&<Button type="link" onClick={openScenariosForDelete} style={{padding:0}}>Перейти к сценариям</Button>}</Space>}/>}
  </Modal>
  <Modal title="Изменить название устройства" open={renameOpen} onCancel={()=>setRenameOpen(false)} onOk={saveRename} okText="Сохранить" okButtonProps={{disabled:renameTitle.trim().length<2}}><Form layout="vertical"><Form.Item label="Название"><Input value={renameTitle} maxLength={80} onChange={e=>setRenameTitle(e.target.value)}/></Form.Item></Form><Text type="secondary">Тип устройства менять нельзя. Чтобы выбрать другой тип, удалите устройство и создайте новое.</Text></Modal>
  <LivePanel open={liveOpen} onClose={()=>setLiveOpen(false)} status={live} devices={devices} onRefresh={refresh}/>
  {scenarioEditorOpen && <ScenarioEditor scenario={scenarioEdit} devices={devices} onClose={()=>setScenarioEditorOpen(false)} onSaved={()=>{setScenarioEditorOpen(false);setScenarioEdit(null);refresh();setPage('scenarios');}}/>}
  </Layout>;
}

function Dashboard({live,devices,scenarios,logs,onOpen,onCreate,onDelete,onQuickComplete}:{live:any;devices:Device[];scenarios:Scenario[];logs:any[];onOpen:(id:string)=>void;onCreate:()=>void;onDelete:(device:Device)=>void;onQuickComplete:()=>Promise<void>}) {
  return <div className="page-wrap"><div className="hero"><div><Title level={2}>Контроль пространства</Title><Text type="secondary">Управляйте виртуальными устройствами на расстоянии.</Text></div><div className="hero-orb"><div className="orb-grid"/><BulbOutlined/></div></div><QuickScenarios onComplete={onQuickComplete}/><Row gutter={[16,16]} className="stats"><Col xs={12} md={6}><Metric label="Устройства" value={devices.length} hint="в локальной сети" icon={<ControlOutlined/>}/></Col><Col xs={12} md={6}><Metric label="Сценарии" value={scenarios.length} hint={`${scenarios.filter(s=>s.enabled).length} активны`} icon={<DeploymentUnitOutlined/>}/></Col><Col xs={12} md={6}><Metric label="Контур" value={live.running ? 'LIVE' : 'LOCAL'} hint={live.connected ? 'связь с Ujin работает' : live.running ? 'подключаемся к Ujin' : 'работает автономно'} icon={<ApiOutlined/>}/></Col><Col xs={12} md={6}><Metric label="События" value={logs.length} hint="в журнале исполнения" icon={<ThunderboltOutlined/>}/></Col></Row><div className="section-head"><div><Title level={4}>Устройства</Title><Text type="secondary">Быстрый доступ к текущему состоянию</Text></div><Button type="primary" icon={<PlusOutlined/>} onClick={onCreate}>Создать устройство</Button></div><Row gutter={[14,14]}>{devices.slice(0,6).map(d=><Col xs={24} sm={12} xl={8} key={d.id}><DeviceCard device={d} onClick={()=>onOpen(d.id)} onDelete={d.deletable?onDelete:undefined}/></Col>)}</Row><div className="section-head"><div><Title level={4}>Журнал событий</Title><Text type="secondary">Обновляется в реальном времени</Text></div></div><LogList logs={logs.slice(0,5)} scenarios={scenarios}/></div>
}
function QuickScenarios({onComplete}:{onComplete:()=>Promise<void>}) {
  const [running,setRunning]=useState<string|null>(null);
  const run=async(id:string)=>{
    if(running)return;
    setRunning(id);
    try {
      const result=await request<{title:string;status:string;results:{status:string;message:string;notification?:ScenarioActionNotice}[]}>(`/quick-scenarios/${id}/run`,{method:'POST'});
      result.results.forEach(row=>{if(row.notification)showScenarioAction(row.notification);});
      const issues=result.results.filter(row=>row.status!=='completed').map(row=>row.message);
      if(result.status==='partial') notification.warning({message:`«${result.title}»: выполнено частично`,description:issues.join(' '),duration:8});
      else if(result.status==='empty') notification.info({message:'Нет подходящих устройств',description:'Добавьте устройства для этого сценария.'});
      await onComplete();
    } catch(e:any){notification.error({message:'Не удалось запустить сценарий',description:e.message});}
    finally{setRunning(null);}
  };
  return <section className="quick-scenarios" aria-label="Быстрые сценарии">
    <div className="section-head"><div><Title level={4}>Быстрые сценарии</Title><Text type="secondary">Одно нажатие — дом готов.</Text></div></div>
    <Row gutter={[16,16]}>{quickScenarios.map(s=><Col xs={24} md={12} key={s.id}>
      <Card className="quick-scenario-card"><div className="quick-scenario-heading"><span className="quick-scenario-icon">{s.id==='quick_home'?<HomeOutlined/>:<MoonOutlined/>}</span><Tag>Закреплено</Tag></div>
        <Title level={4}>{s.title}</Title><Typography.Paragraph type="secondary">{s.description}</Typography.Paragraph>
        <Button type="primary" size="large" block loading={running===s.id} disabled={Boolean(running&&running!==s.id)} onClick={()=>run(s.id)}>{s.title}</Button>
      </Card>
    </Col>)}</Row>
  </section>;
}
function Metric({label,value,hint,icon}:{label:string;value:any;hint:string;icon:any}){return <Card className="metric-card"><div className="metric-icon">{icon}</div><Text type="secondary">{label}</Text><div className="metric-number">{value}</div><small>{hint}</small></Card>}
function DeviceCard({device,onClick,onDelete}:{device:Device;onClick:()=>void;onDelete?:(device:Device)=>void}){
  const signal=getPrimarySignal(device);
  const status=signal?formatSignalValue(signal,device.state[signal.name]):'Нет данных';
  return <Card hoverable className="device-card" onClick={onClick}>
    <div className="card-top"><span className="device-glyph"><IconFor device={device}/></span><Space size={8}>{onDelete&&device.deletable&&<Button className="device-card-delete" size="small" danger icon={<DeleteOutlined/>} aria-label={`Удалить ${device.title}`} title="Удалить устройство" onClick={event=>{event.stopPropagation();onDelete(device);}}/>}<Tag bordered={false} color="green">В сети</Tag></Space></div>
    <Title level={5} className="device-card-title">{device.title}</Title>
    <div className="device-primary-state">{status}</div>
    <div className="card-action">Открыть панель <span>↗</span></div>
  </Card>;
}
function IconFor({device,type:explicitType}:{device?:Device;type?:string}){
  const type=explicitType||device?.type||device?.model||'';
  if(type.includes('barrier'))return <span className="device-neon-icon barrier-neon-icon"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 21V9h3v12M19 21v-9"/><path d="M6.5 9 19 5.5v2L6.5 11Z"/><path d="m10 8 1 2m2-3 1 2m2-3 1 2"/></svg></span>;
  if(type.includes('thermostat'))return <span className="device-neon-icon thermometer-neon-icon"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0Z"/><path d="M12 11v6"/></svg></span>;
  const icon=type.includes('kettle')?<CoffeeOutlined/>:
    type.includes('curtain')?<PicCenterOutlined/>:
    type.includes('light')?<BulbOutlined/>:
    type.includes('leak')?<ApiOutlined/>:
    type.includes('valve')?<ApiOutlined/>:
    <ThunderboltOutlined/>;
  return <span className="device-neon-icon">{icon}</span>;
}
function DevicesPage({devices,selected,onOpen,onBack,onCommand,onSimulate,onBuild,onEditDevice,onDeleteDevice}:{devices:Device[];selected:Device|null;onOpen:(id:string)=>void;onBack:()=>void;onCommand:(d:Device,s:Signal,v:any)=>void;onSimulate:(d:Device,v:number)=>void;onBuild:()=>void;onEditDevice:(d:Device)=>void;onDeleteDevice:(d:Device)=>void}){
  if(!selected)return <div className="page-wrap"><div className="section-head page-title"><div><Title level={2}>Устройства</Title><Text type="secondary">Состояния и управление устройствами</Text></div><Button type="primary" icon={<PlusOutlined/>} onClick={onBuild}>Создать устройство</Button></div><Row gutter={[14,14]}>{devices.map(d=><Col xs={24} sm={12} xl={8} key={d.id}><DeviceCard device={d} onClick={()=>onOpen(d.id)} onDelete={d.deletable?onDeleteDevice:undefined}/></Col>)}</Row></div>;
  const visible=getVisibleSignals(selected);
  const sections=[...new Set(visible.map(s=>s.section || groups[s.group] || 'Сведения'))];
  return <div className="page-wrap"><Button type="link" onClick={onBack}>← Все устройства</Button><div className="device-detail-head"><div><Tag color="green">В сети</Tag><Title level={2}>{selected.title}</Title></div><Space wrap>{selected.type==='leak'&&<Button onClick={()=>onSimulate(selected,1)}>Сымитировать протечку</Button>}{selected.type==='leak'&&<Button onClick={()=>onSimulate(selected,0)}>Сбросить датчик</Button>}{selected.user_created&&<Button onClick={()=>onEditDevice(selected)}>Изменить название</Button>}{selected.deletable&&<Button danger icon={<DeleteOutlined/>} onClick={()=>onDeleteDevice(selected)}>Удалить</Button>}</Space></div><Row gutter={16}><Col xs={24} xl={17}>{sections.map(section=>{const sigs=visible.filter(s=>(s.section || groups[s.group] || 'Сведения')===section);if(!sigs.length)return null;return <section className="signal-section" key={section}><div className="section-head"><Title level={4}>{section}</Title></div><Row gutter={[12,12]}>{sigs.map(s=><Col xs={24} md={12} key={s.name}><SignalCard device={selected} signal={s} value={selected.state[s.name]} onCommand={onCommand}/></Col>)}</Row></section>})}</Col><Col xs={24} xl={7}><Card className="detail-side"><Title level={5}>Сведения</Title><Descriptions column={1} size="small"><Descriptions.Item label="Название">{selected.title}</Descriptions.Item><Descriptions.Item label="Тип">{selected.preset_title || selected.title}</Descriptions.Item><Descriptions.Item label="Возможностей">{visible.length}</Descriptions.Item><Descriptions.Item label="Подключение">Локальное</Descriptions.Item></Descriptions></Card></Col></Row></div>
}
function SignalCard({device,signal,value,onCommand}:{device:Device;signal:Signal;value:any;onCommand:(d:Device,s:Signal,v:any)=>void}){
  const writable=['rw','w'].includes(signal.management);
  const [rangeValue,setRangeValue]=useState(Number.isFinite(Number(value))?Number(value):0);
  useEffect(()=>{setRangeValue(Number.isFinite(Number(value))?Number(value):0);},[value]);
  let editor:any=null;
  const opts=signal.layout?Object.keys(signal.layout).filter(v=>signal.control!=='combolist'||Number(v)>0).map(v=>({value:Number(v),label:formatSignalValue(signal,v)})):[];
  if(writable){
    if(signal.control==='switch') editor=<Space><Switch checked={!!Number(value)} onChange={v=>onCommand(device,signal,v?1:0)}/><Text>{formatSignalValue(signal,value)}</Text></Space>;
    else if(signal.control==='range') editor=<div className="range-control"><Slider min={signal.min??0} max={signal.max??100} value={rangeValue} onChange={setRangeValue} onChangeComplete={v=>onCommand(device,signal,v)}/><Text>{formatSignalValue(signal,rangeValue)}</Text></div>;
    else if(signal.control==='push_time') editor=<Button type="primary" onClick={()=>onCommand(device,signal,1)}>{signal.name==='self_test'?'Запустить проверку':signal.title}</Button>;
    else if(signal.control==='counter'||signal.control==='number') editor=<InputNumber min={signal.min} max={signal.max} value={Number(value)} onChange={v=>v!==null&&onCommand(device,signal,v)}/>;
    else if(opts.length) editor=<Select value={Number(value)} options={opts} onChange={v=>onCommand(device,signal,v)} style={{minWidth:130}}/>;
    else editor=<Input value={String(value)} onPressEnter={e=>onCommand(device,signal,(e.target as HTMLInputElement).value)}/>;
  }
  return <Card size="small" className="signal-card"><div><Text strong>{signal.title}</Text></div><div className="signal-control">{writable?editor:<b>{formatSignalValue(signal,value)}</b>}</div></Card>;
}
function ScenarioPage({scenarios,devices,logs,onEdit,onRefresh,onDelete}:{scenarios:Scenario[];devices:Device[];logs:any[];onEdit:(s:Scenario|null)=>void;onRefresh:()=>void;onDelete:(s:Scenario)=>Promise<void>}){
  const [helpOpen,setHelpOpen]=useState(false);
  const [deleteTarget,setDeleteTarget]=useState<Scenario|null>(null);
  const [deleteBusy,setDeleteBusy]=useState(false);
  const [deleteError,setDeleteError]=useState('');
  const closeDelete=()=>{if(!deleteBusy){setDeleteTarget(null);setDeleteError('');}};
  const confirmDelete=async()=>{
    if(!deleteTarget||deleteBusy)return;
    setDeleteBusy(true);setDeleteError('');
    try{await onDelete(deleteTarget);setDeleteTarget(null);}
    catch(e:any){setDeleteError(e?.message||'Не удалось удалить сценарий. Попробуйте ещё раз.');}
    finally{setDeleteBusy(false);}
  };

  const toggle=async(s:Scenario)=>{try{await request(`/scenarios/${s.id}/${s.enabled?'disable':'enable'}`,{method:'POST'});onRefresh();}catch(e:any){notification.error({message:e.message})}};
  const test=async(s:Scenario)=>{try{await request(`/scenarios/${s.id}/test`,{method:'POST'});notification.success({message:'Тест сценария запущен'});onRefresh();}catch(e:any){notification.error({message:e.message})}};
  return <div className="page-wrap"><div className="section-head page-title"><div><Title level={2}>Сценарии</Title><Text type="secondary">Выберите событие, при необходимости добавьте проверку и задайте действие.</Text></div><Space><Button icon={<QuestionCircleOutlined/>} onClick={()=>setHelpOpen(true)}>Как это работает</Button><Button type="primary" icon={<PlusOutlined/>} onClick={()=>onEdit(null)}>Новый сценарий</Button></Space></div><Row gutter={16}><Col xs={24} xl={15}><Space direction="vertical" size={12} style={{width:'100%'}}>{scenarios.length?scenarios.map(s=><Card className="scenario-card" key={s.id}><div className="scenario-row"><div><Text type="secondary" className="micro">{s.execution_mode==='live'?'ПЛАТФОРМА UJIN':'ЛОКАЛЬНЫЙ СЦЕНАРИЙ'}</Text><Title level={5}>{s.title}</Title><Text>{scenarioSummary(s,devices)}</Text></div><Space wrap><Switch checked={s.enabled} onChange={()=>toggle(s)} checkedChildren="Вкл" unCheckedChildren="Выкл"/><Button onClick={()=>test(s)}>Проверить</Button><Button onClick={()=>onEdit(s)}>Изменить</Button><Button onClick={async()=>{try{await request<any>(`/live/scenarios/${s.id}/deploy`,{method:'POST'});notification.success({message:'Сценарий отправлен в Ujin'});}catch(e:any){notification.error({message:'LIVE недоступен',description:e.message})}}}>В LIVE</Button><Button danger icon={<DeleteOutlined/>} onClick={()=>{setDeleteTarget(s);setDeleteError('');}}>Удалить</Button></Space></div><div className="flow-summary"><Tag color="blue">КОГДА</Tag><span>⟶</span>{(s.condition||s.conditions?.length)&&<><Tag color="gold">ЕСЛИ</Tag><span>⟶</span></>}<Tag color="green">ТОГДА</Tag><span className="flow-line"/></div></Card>):<EmptyCard title="Пока нет сценариев" description="Создайте первое правило автоматизации." onClick={()=>onEdit(null)}/>}</Space></Col><Col xs={24} xl={9}><Card className="log-card"><div className="section-head"><div><Title level={4}>Выполнение</Title><Text type="secondary">Последние события автоматизаций</Text></div><Tag color="cyan">ЖУРНАЛ</Tag></div><LogList logs={logs.slice(0,18)} scenarios={scenarios}/></Card></Col></Row><Modal open={Boolean(deleteTarget)} title="Удалить сценарий?" okText="Удалить" cancelText="Отмена" okButtonProps={{danger:true}} cancelButtonProps={{disabled:deleteBusy}} confirmLoading={deleteBusy} closable={!deleteBusy} maskClosable={!deleteBusy} keyboard={!deleteBusy} onCancel={closeDelete} onOk={confirmDelete}>
    {deleteTarget&&<Typography.Paragraph>Сценарий «{deleteTarget.title}» будет удалён и больше не будет запускаться в приложении.</Typography.Paragraph>}
    {deleteTarget?.ujin_id&&<Alert type="warning" showIcon message="Копия сценария в Ujin останется на платформе."/>}
    {deleteError&&<Alert type="error" showIcon message="Не удалось удалить сценарий" description={deleteError}/>}
  </Modal><HelpDrawer open={helpOpen} onClose={()=>setHelpOpen(false)} kind="scenario"/></div>
}
function scenarioSummary(s:Scenario,devices:Device[]){return formatScenarioHumanReadable(s.trigger,s.condition||s.conditions?.[0]||null,s.action||s.actions?.[0],devices);}
function LogList({logs,scenarios=[]}:{logs:any[];scenarios?:Scenario[]}){return <div className="log-list">{logs.length?logs.map((l,i)=><div className="log-row" key={`${l.time}-${i}`}><i className={`log-dot ${l.node_id||l.status||''}`}/><div><b>{l.message||l.status||'Событие'}</b><small>{new Date(l.time).toLocaleTimeString('ru-RU')} · {scenarios.find(s=>s.id===l.scenario_id)?.title||quickScenarios.find(s=>s.id===l.scenario_id)?.title||'Автоматизация'}</small></div></div>):<Text type="secondary">Событий пока нет</Text>}</div>}
function EmptyCard({title,description,onClick}:{title:string;description:string;onClick:()=>void}){return <Card className="empty-card"><div>⌘</div><Title level={4}>{title}</Title><Text type="secondary">{description}</Text><br/><Button type="primary" onClick={onClick}>Создать</Button></Card>}
function DevicePresetFlow({open,onClose,onDone}:{open:boolean;onClose:()=>void;onDone:(id?:string)=>void}){
  const [presets,setPresets]=useState<DevicePreset[]>([]);const [selected,setSelected]=useState<DevicePreset|null>(null);const [title,setTitle]=useState('');const [loading,setLoading]=useState(false);
  useEffect(()=>{if(!open)return;setSelected(null);setTitle('');request<DevicePreset[]>('/device-presets').then(setPresets).catch((e:any)=>notification.error({message:'Не удалось загрузить типы устройств',description:e.message}));},[open]);
  const add=async()=>{if(!selected||title.trim().length<2)return;setLoading(true);try{const created=await request<Device>('/devices',{method:'POST',body:JSON.stringify({type:selected.type,title:title.trim()})});notification.success({message:'Устройство добавлено',description:`${selected.title} «${created.title}» доступен в сценариях.`});onDone(created.id);}catch(e:any){notification.error({message:'Не удалось добавить устройство',description:e.message});}finally{setLoading(false)}};
  return <Modal open={open} onCancel={onClose} footer={null} width={820} destroyOnClose title={selected?'Добавление устройства':'Какое устройство вы хотите добавить?'} className="preset-modal">
    {!selected?<><Text type="secondary">Выберите тип — возможности и настройки уже подготовлены.</Text><Row gutter={[14,14]} style={{marginTop:20}}>{presets.map(p=><Col xs={24} sm={12} md={6} key={p.type}><Card hoverable className="preset-choice" onClick={()=>{setSelected(p);setTitle(p.title);}}><span className="preset-icon"><IconFor type={p.type}/></span><Title level={5}>{p.title}</Title></Card></Col>)}</Row></>:<><div className="preset-selected"><span className="preset-icon"><IconFor type={selected.type}/></span><div><Text type="secondary">Тип устройства</Text><Title level={4}>{selected.title}</Title></div></div><Form layout="vertical" style={{marginTop:20}}><Form.Item label="Название" required><Input size="large" maxLength={80} value={title} onChange={e=>setTitle(e.target.value)} placeholder={`Например, ${selected.title.toLocaleLowerCase('ru-RU')} в прихожей`}/></Form.Item></Form><Title level={5}>Что умеет устройство</Title><Row gutter={[20,10]}>{Object.entries(selected.features).map(([group,features])=><Col xs={24} sm={12} key={group}><div className="preset-feature-group"><Text strong>{group}</Text>{features.map(feature=><div className="preset-feature" key={feature}><span>✓</span>{feature}</div>)}</div></Col>)}</Row><div className="preset-actions"><Button onClick={()=>{setSelected(null);setTitle('');}}>Назад</Button><Button type="primary" loading={loading} disabled={title.trim().length<2} onClick={add}>Добавить устройство</Button></div></>}
  </Modal>;
}

function makeGraph(hasCondition:boolean):{nodes:Node[];edges:Edge[]}{
  const nodes:Node[]=[{id:'event',type:'input',position:{x:35,y:54},data:{label:'КОГДА'}},...(hasCondition?[{id:'condition',position:{x:310,y:54},data:{label:'ЕСЛИ'}} as Node]:[]),{id:'action',type:'output',position:{x:hasCondition?590:390,y:54},data:{label:'ТОГДА'}}];
  const edge=(id:string,source:string,target:string):Edge=>({id,source,target,animated:true,markerEnd:{type:MarkerType.ArrowClosed}});
  return {nodes,edges:hasCondition?[edge('e1','event','condition'),edge('e2','condition','action')]:[edge('e1','event','action')]};
}
function normalizeGraphLabels(graph:Node[],hasCondition:boolean){
  const labels:Record<string,string>={event:'КОГДА',trigger:'КОГДА',condition:'ЕСЛИ',action:'ТОГДА',then:'ТОГДА'};
  return graph.map(node=>({...node,data:{...node.data,label:labels[node.id]||(node.id.toLowerCase().includes('condition')?'ЕСЛИ':node.id.toLowerCase().includes('action')?'ТОГДА':'КОГДА')}}));
}
function isValueValid(signal:Signal|undefined,value:any){
  if(!signal||value===undefined||value===null||value==='')return false;
  if(signal.event_title&&isCommandSignal(signal))return true;
  if(isNumericSignal(signal)){const n=Number(value);return Number.isFinite(n)&&(signal.min===undefined||n>=signal.min)&&(signal.max===undefined||n<=signal.max);}
  if(isEnumSignal(signal))return Object.prototype.hasOwnProperty.call(signal.layout,String(value));
  return true;
}

function HelpDrawer({open,onClose,kind}:{open:boolean;onClose:()=>void;kind:'scenario'|'device'}){
  return <Drawer title="Как создать сценарий" width={440} open={open} onClose={onClose}><Typography.Paragraph>Сценарий связывает событие и действие простыми правилами.</Typography.Paragraph><ol><li><b>Когда</b> — выберите событие, которое запускает автоматизацию.</li><li><b>Если</b> — при необходимости добавьте дополнительную проверку.</li><li><b>Тогда</b> — выберите действие системы.</li></ol><Alert type="info" showIcon message="Например" description="Когда датчик протечки обнаружит воду, включить свет."/></Drawer>;
}

function ScenarioEditor({scenario,devices,onClose,onSaved}:{scenario:Scenario|null;devices:Device[];onClose:()=>void;onSaved:()=>void}){
  const existingCondition=scenario?.condition||scenario?.conditions?.[0]||null;
  const [title,setTitle]=useState(scenario?.title||'');const [titleEdited,setTitleEdited]=useState(Boolean(scenario?.title));
  const [trigger,setTrigger]=useState<Rule>(scenario?.trigger||{device_id:'',signal:'',operator:'==',value:1});
  const [condition,setCondition]=useState<Rule|null>(existingCondition);
  const [action,setAction]=useState<any>(scenario?.action||scenario?.actions?.[0]||{device_id:'',signal:'',value:undefined});
  const [showInstructions,setShowInstructions]=useState(true);const [helpOpen,setHelpOpen]=useState(false);
  const initialGraph=scenario?.graph?.nodes?.length?{nodes:normalizeGraphLabels(scenario.graph.nodes,Boolean(existingCondition)),edges:scenario.graph.edges}:makeGraph(Boolean(existingCondition));
  const [nodes,setNodes,onNodesChange]=useNodesState(initialGraph.nodes);const [edges,setEdges,onEdgesChange]=useEdgesState(initialGraph.edges);
  const triggerDevice=devices.find(d=>d.id===trigger.device_id);const conditionDevice=devices.find(d=>d.id===condition?.device_id);const actionDevice=devices.find(d=>d.id===action.device_id);
  const triggerSignal=triggerDevice?.declaration.find(s=>s.name===trigger.signal);const conditionSignal=conditionDevice?.declaration.find(s=>s.name===condition?.signal);const actionSignal=actionDevice?.declaration.find(s=>s.name===action.signal);
  const makeTrigger=(device_id:string,signal=''):Rule=>({device_id,signal,operator:'==',value:1});
  const selectTriggerDevice=(id:string)=>setTrigger(makeTrigger(id));
  const selectTriggerSignal=(name:string)=>{const signal=triggerDevice?.declaration.find(s=>s.name===name);setTrigger({device_id:trigger.device_id,signal:name,operator:'==',value:signal&&isBooleanSignal(signal)?1:signal?getDefaultRuleValue(signal):''});};
  const selectConditionDevice=(id:string)=>setCondition(makeTrigger(id,''));
  const selectConditionSignal=(name:string)=>{const signal=conditionDevice?.declaration.find(s=>s.name===name);setCondition({device_id:condition?.device_id||'',signal:name,operator:'==',value:signal&&isBooleanSignal(signal)?1:signal?getDefaultRuleValue(signal):''});};
  const selectActionDevice=(id:string)=>setAction({device_id:id,signal:'',value:undefined});
  const selectActionSignal=(name:string)=>{const signal=actionDevice?.declaration.find(s=>s.name===name);setAction({device_id:action.device_id,signal:name,value:signal?getActionDefault(signal,actionDevice):undefined});};
  const toggleCondition=(enabled:boolean)=>{setCondition(enabled?{device_id:'',signal:'',operator:'==',value:1}:null);const graph=makeGraph(enabled);setNodes(graph.nodes);setEdges(graph.edges);};
  const onConnect=(connection:Connection)=>setEdges(current=>addEdge({...connection,animated:true,markerEnd:{type:MarkerType.ArrowClosed},style:{stroke:'#39c8ff'}},current));
  const suggestedTitle=triggerSignal&&actionSignal?`${formatRulePhrase(trigger,devices).replace(/^./,c=>c.toLocaleUpperCase('ru-RU'))} → ${formatActionPhrase(action,devices)}`:'';
  const displayedTitle=titleEdited?title:suggestedTitle;
  const isComplete=Boolean(displayedTitle?.trim()&&triggerDevice&&triggerSignal&&isValueValid(triggerSignal,trigger.value)&&(!condition||(conditionDevice&&conditionSignal&&isValueValid(conditionSignal,condition.value)))&&actionDevice&&actionSignal&&(isCommandSignal(actionSignal)||isValueValid(actionSignal,action.value)));
  const preview=isComplete?formatScenarioHumanReadable(trigger,condition,action,devices):'Выберите событие и действие, чтобы увидеть описание сценария.';
  const save=async()=>{
    if(!isComplete)return;
    const payload:any={...(scenario||{}),id:scenario?.id,title:(displayedTitle||'Новый сценарий').trim(),enabled:scenario?.enabled??true,execution_mode:scenario?.execution_mode||'local',trigger,graph:{nodes,edges}};
    if(scenario?.actions)payload.actions=[action];else payload.action=action;
    if(condition){
      if(scenario?.condition&&!scenario?.conditions)payload.condition=condition;
      else {
        const remainingConditions=scenario?.condition
          ?(scenario.conditions||[])
          :(scenario?.conditions||[]).slice(1);
        payload.conditions=[condition,...remainingConditions];
      }
    }else{delete payload.condition;delete payload.conditions;}
    try{await request(scenario?`/scenarios/${scenario.id}`:'/scenarios',{method:scenario?'PUT':'POST',body:JSON.stringify(payload)});notification.success({message:'Сценарий сохранён'});onSaved();}catch(e:any){notification.error({message:'Не удалось сохранить сценарий',description:e.message})}
  };
  return <Modal title={scenario?'Редактировать сценарий':'Новый сценарий'} open onCancel={onClose} onOk={save} okText="Сохранить" okButtonProps={{disabled:!isComplete}} width={980} className="scenario-modal">
    <Form layout="vertical" className="scenario-editor-form">
      <Form.Item label="Название сценария" validateStatus={displayedTitle?.trim()?'success':'error'} help={!displayedTitle?.trim()?'Выберите событие и действие или введите название.':undefined}><Input size="large" value={displayedTitle} onChange={e=>{setTitle(e.target.value);setTitleEdited(true);}} placeholder="Название появится после настройки события и действия"/></Form.Item>
      {showInstructions&&<Alert className="scenario-instructions" type="info" showIcon icon={<InfoCircleOutlined/>} closable onClose={()=>setShowInstructions(false)} message="Как настроить сценарий" description={<><span>1. Выберите событие, которое должно произойти. 2. При необходимости добавьте условие. 3. Выберите действие системы.</span><br/><small>Например: когда обнаружена протечка → тогда включить свет.</small></>}/>}
      <div className="flow-canvas flow-canvas-compact"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} fitView minZoom={0.6} maxZoom={1.4}><Background color="#18334a" gap={22}/></ReactFlow></div>
      <section className="editor-step"><div className="editor-step-heading"><span className="step-number blue">1</span><div><Title level={4}>КОГДА</Title><Text type="secondary">Выберите событие, которое запустит сценарий.</Text></div></div>
        <Row gutter={12}><Col xs={24} md={12}><Form.Item label="Устройство" validateStatus={!trigger.device_id?'error':undefined} help={!trigger.device_id?'Выберите устройство для события.':undefined}><DeviceSelect devices={devices} value={trigger.device_id} onChange={selectTriggerDevice}/></Form.Item></Col><Col xs={24} md={12}><Form.Item label="Событие" validateStatus={trigger.device_id&&!trigger.signal?'error':undefined} help={trigger.device_id&&!trigger.signal?'Выберите состояние или показание.':undefined}><SignalSelect device={triggerDevice} context="trigger" value={trigger.signal} disabled={!trigger.device_id} onChange={selectTriggerSignal}/></Form.Item></Col></Row>
        {triggerSignal&&<RuleValueFields signal={triggerSignal} value={trigger.value} operator={trigger.operator} onChange={patch=>setTrigger({...trigger,...patch})} role="события"/>}
      </section>
      <section className="editor-step condition-step"><div className="editor-step-heading"><span className="step-number gold">2</span><div><Title level={4}>ЕСЛИ <small className="technical-kicker">НЕОБЯЗАТЕЛЬНО</small></Title><Text type="secondary">Дополнительная проверка перед выполнением действия.</Text></div></div>
        <div className="condition-toggle"><div><b>Использовать дополнительное условие</b><small>Сценарий сработает, только если это условие выполнено.</small></div><Switch checked={Boolean(condition)} onChange={toggleCondition}/></div>
        {condition&&<><Row gutter={12}><Col xs={24} md={12}><Form.Item label="Устройство" validateStatus={!condition.device_id?'error':undefined} help={!condition.device_id?'Выберите устройство для проверки.':undefined}><DeviceSelect devices={devices} value={condition.device_id} onChange={selectConditionDevice}/></Form.Item></Col><Col xs={24} md={12}><Form.Item label="Проверяемое состояние" validateStatus={condition.device_id&&!condition.signal?'error':undefined} help={condition.device_id&&!condition.signal?'Выберите состояние или показание.':undefined}><SignalSelect device={conditionDevice} context="condition" value={condition.signal} disabled={!condition.device_id} onChange={selectConditionSignal}/></Form.Item></Col></Row>{conditionSignal&&<RuleValueFields signal={conditionSignal} value={condition.value} operator={condition.operator} onChange={patch=>setCondition({...condition,...patch})} role="условия"/>}</>}
      </section>
      <section className="editor-step action-step"><div className="editor-step-heading"><span className="step-number green">3</span><div><Title level={4}>ТОГДА</Title><Text type="secondary">Выберите, что система должна сделать.</Text></div></div>
        <Row gutter={12}><Col xs={24} md={12}><Form.Item label="Устройство" validateStatus={!action.device_id?'error':undefined} help={!action.device_id?'Выберите устройство для действия.':undefined}><DeviceSelect devices={devices} value={action.device_id} onChange={selectActionDevice}/></Form.Item></Col><Col xs={24} md={12}><Form.Item label="Действие" validateStatus={action.device_id&&!action.signal?'error':undefined} help={action.device_id&&!action.signal?'Выберите доступное действие.':undefined}><SignalSelect device={actionDevice} context="action" value={action.signal} disabled={!action.device_id} onChange={selectActionSignal}/></Form.Item></Col></Row>
        {actionSignal&&<ActionValueFields signal={actionSignal} value={action.value} onChange={value=>setAction({...action,value})}/>}
      </section>
      <div className="scenario-preview"><div><InfoCircleOutlined/><b>Ваш сценарий</b></div><p>{preview}</p></div>
      {!isComplete&&<Text className="save-hint" type="secondary">Заполните событие и действие, чтобы сохранить сценарий.</Text>}
      <Button type="link" icon={<QuestionCircleOutlined/>} onClick={()=>setHelpOpen(true)}>Как создать сценарий</Button>
    </Form>
    <HelpDrawer open={helpOpen} onClose={()=>setHelpOpen(false)} kind="scenario"/>
  </Modal>;
}

function DeviceSelect({devices,value,onChange}:{devices:Device[];value:string;onChange:(value:string)=>void}){
  return <Select allowClear placeholder="Выберите устройство" value={value||undefined} onChange={onChange} options={devices.map(device=>({value:device.id,label:device.title}))} />;
}
function SignalSelect({device,context,value,onChange,disabled}:{device?:Device;context:SignalContext;value:string;onChange:(value:string)=>void;disabled:boolean}){
  const signals=getAvailableSignals(device,context);
  const labelFor=(signal:Signal)=>context==='action'?(signal.action_title||signal.title):(context==='trigger'?(signal.event_title||signal.title):signal.title);
  const groups=[{label:context==='action'?'Доступные действия':'Состояния и показания',options:signals.map(signal=>({value:signal.name,label:labelFor(signal),signal}))}];
  return <Select allowClear disabled={disabled||!signals.length} placeholder={disabled?'Сначала выберите устройство':context==='action'?'Выберите действие':'Выберите состояние или событие'} value={value||undefined} onChange={onChange} options={groups} optionLabelProp="label" optionRender={({data}:any)=><div className="signal-option"><b>{labelFor(data.signal)}</b><small>{data.signal.description||data.signal.section||'Возможность устройства'}{data.signal.measure?` · ${data.signal.measure}`:''}</small></div>} popupMatchSelectWidth={false} listHeight={280} placement="bottomLeft" getPopupContainer={node=>node.closest('.ant-modal-content')||document.body} popupClassName="scenario-select-popup"/>;
}
function RuleValueFields({signal,value,operator,onChange,role}:{signal:Signal;value:any;operator:string;onChange:(patch:Partial<Rule>)=>void;role:string}){
  if(signal.event_title&&isCommandSignal(signal))return <Alert type="info" showIcon message={`Событие «${signal.event_title}» запускает сценарий при каждом срабатывании.`}/>;
  if(isBooleanSignal(signal)||isEnumSignal(signal)){
    const options=isBooleanSignal(signal)?[{value:1,label:/протеч|вода|leak/i.test(`${signal.name} ${signal.title}`)?'Обнаружена':/свет|ламп|light|lamp/i.test(`${signal.name} ${signal.title}`)?'Вкл':'Да'},{value:0,label:/протеч|вода|leak/i.test(`${signal.name} ${signal.title}`)?'Не обнаружена':/свет|ламп|light|lamp/i.test(`${signal.name} ${signal.title}`)?'Выкл':'Нет'}]:Object.keys(signal.layout||{}).map(key=>({value:Number(key),label:formatSignalValue(signal,key)}));
    return <Form.Item label={isBooleanSignal(signal)?'Состояние':'Значение'} validateStatus={!isValueValid(signal,value)?'error':undefined} help={!isValueValid(signal,value)?`Выберите значение ${role}.`:undefined}><Select disabled={!signal} value={value===undefined||value===null?undefined:Number(value)} onChange={v=>onChange({operator:'==',value:v})} options={options}/></Form.Item>;
  }
  const operators=isNumericSignal(signal)?[['==','Равно'],['!=','Не равно'],['>','Больше'],['<','Меньше'],['>=','Больше или равно'],['<=','Меньше или равно']]:[['==','Равно'],['!=','Не равно']];
  const numeric=isNumericSignal(signal);
  return <Row gutter={12}><Col xs={24} md={numeric?9:10}><Form.Item label="Условие"><Select value={operator||'=='} onChange={v=>onChange({operator:v})} options={operators.map(([v,label])=>({value:v,label}))}/></Form.Item></Col><Col xs={24} md={numeric?15:14}><Form.Item label={signal.title} validateStatus={!isValueValid(signal,value)?'error':undefined} help={!isValueValid(signal,value)?signal.min!==undefined||signal.max!==undefined?`Допустимо: ${signal.min??'…'}–${signal.max??'…'}${signal.measure?` ${signal.measure}`:''}`:'Укажите значение.':undefined}><Input value={value??''} onChange={e=>onChange({value:e.target.value})} addonAfter={signal.measure||undefined} placeholder={numeric?'Введите число':'Введите текст'} type={numeric?'number':'text'} min={signal.min} max={signal.max}/></Form.Item></Col></Row>;
}
function ActionValueFields({signal,value,onChange}:{signal:Signal;value:any;onChange:(value:any)=>void}){
  if(isCommandSignal(signal))return <Alert className="command-note" type="success" showIcon message={`Команда «${signal.title}» будет выполнена без дополнительных параметров.`}/>;
  if(isBooleanSignal(signal))return <Form.Item label={signal.action_title||signal.title}><Select value={Number(value)} onChange={onChange} options={[{value:1,label:signal.action_on||'Включить'},{value:0,label:signal.action_off||'Выключить'}]}/></Form.Item>;
  if(isEnumSignal(signal))return <Form.Item label={signal.action_title||signal.title}><Select value={value===undefined?undefined:Number(value)} onChange={onChange} options={Object.keys(signal.layout||{}).filter(v=>signal.control!=='combolist'||Number(v)>0).map(v=>({value:Number(v),label:formatSignalValue(signal,v)}))}/></Form.Item>;
  return <Form.Item label={isNumericSignal(signal)?`Установить ${signal.title.toLocaleLowerCase('ru-RU')}`:signal.title} validateStatus={!isValueValid(signal,value)?'error':undefined} help={!isValueValid(signal,value)?`Укажите значение${signal.min!==undefined||signal.max!==undefined?` от ${signal.min??'…'} до ${signal.max??'…'}`:''}.`:undefined}><InputNumber className="action-number" value={value} min={signal.min} max={signal.max} addonAfter={signal.measure||undefined} onChange={v=>onChange(v)} placeholder="Введите значение"/></Form.Item>;
}
function NodeConfig({label,accent,children}:{label:string;accent:string;children:any}){return <Card size="small" className={`node-config-card ${accent}`}><Text className="node-label">{label}</Text><Space direction="vertical" style={{width:'100%'}}>{children}</Space></Card>}
