import { useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Collapse, Descriptions, Divider, Drawer, Form, Input, InputNumber, Layout, Menu, Modal, notification, Row, Select, Slider, Space, Switch, Tag, Tooltip, Typography } from 'antd';
import { ApiOutlined, AppstoreOutlined, BulbOutlined, ControlOutlined, DeleteOutlined, DeploymentUnitOutlined, InfoCircleOutlined, PlusOutlined, QuestionCircleOutlined, ThunderboltOutlined, ToolOutlined } from '@ant-design/icons';
import { Background, Controls, MarkerType, ReactFlow, addEdge, useEdgesState, useNodesState, type Connection, type Edge, type Node } from '@xyflow/react';
import { request, wsUrl } from './api';

const { Sider, Header, Content } = Layout;
const { Title, Text } = Typography;
type Signal = { name: string; title: string; description?: string; control: string; management: string; kind: string; group: string; measure?: string; min?: number; max?: number; layout?: Record<string, string> };
type Device = { id: string; title: string; model: string; state: Record<string, any>; declaration: Signal[]; source: string };
type Scenario = { id: string; title: string; enabled: boolean; execution_mode: string; trigger: any; condition?: any; conditions?: any[]; action?: any; actions?: any[]; graph?: { nodes: Node[]; edges: Edge[] } };
type SignalContext = 'trigger' | 'condition' | 'action';
type Rule = { device_id: string; signal: string; operator: string; value: any };
type Parameter = { name: string; title: string; control: string; management: string; kind: string; value: any; measure?: string; min?: number; max?: number; layout?: Record<string,string> };
const groups: Record<string, string> = { property: 'Свойства', capability: 'Возможности', setting: 'Настройки' };

const operatorLabels: Record<string,string> = { '==':'Равно', eq:'Равно', '!=':'Не равно', ne:'Не равно', '>':'Больше', gt:'Больше', '<':'Меньше', lt:'Меньше', '>=':'Больше или равно', gte:'Больше или равно', '<=':'Меньше или равно', lte:'Меньше или равно' };
const typeLabels: Record<string,string> = { switch:'Переключатель', range:'Бегунок', number:'Число', counter:'Счётчик', list:'Список вариантов', text:'Текст', push_time:'Команда', graph:'Числовое значение' };
const accessLabels: Record<string,string> = { r:'Только чтение', rw:'Чтение и управление', w:'Только команда' };
const controlHelp: Record<string,string> = {
  switch:'Переключатель Вкл/Выкл. Подходит для света, реле или другого управляемого состояния.',
  range:'Бегунок для числа в диапазоне, например яркости. Границы задаются в дополнительных настройках; если их не задать, будет диапазон 0–100.',
  number:'Число: температура, напряжение или другое единичное показание/значение.',
  counter:'Числовой счётчик с единицей измерения. Сам по себе не увеличивается: виртуальному устройству нужна отдельная логика обновления.',
  list:'Выбор одного состояния из заданных вариантов: например «Авто», «Ручной», «Выкл».',
  text:'Текстовое значение, например название или короткое сообщение.',
  push_time:'Разовая команда без значения: например «Открыть» или «Самотест».',
};
const roleHelp: Record<string,string> = {
  property:'Показание или состояние, которое устройство сообщает: температура, протечка, заряд.',
  capability:'Управление устройством: свет, реле, команда открытия. Сигнал появится в разделе «Возможности».',
  setting:'Настройка поведения устройства: порог, целевая температура или период отчёта. Появится в разделе «Настройки».',
};
const accessHelp: Record<string,string> = {
  r:'Значение только показывается. Обычно это показание датчика.',
  rw:'Значение показывается и его можно менять вручную или сценарием.',
  w:'Разовая команда. Её можно вызвать, но устройство не хранит обычное состояние по этому параметру.',
};

export function getAvailableSignals(device: Device | undefined, context: SignalContext): Signal[] {
  if (!device) return [];
  return device.declaration.filter(signal => {
    if (signal.name === 'fw') return false;
    const commandLike = signal.control === 'push_time' || signal.control === 'button' || /_cmd$/i.test(signal.name);
    if (context === 'action') return ['rw','w'].includes(signal.management);
    return ['r','rw'].includes(signal.management) && !commandLike;
  });
}

function getVisibleSignals(device: Device) {
  return device.declaration.filter(signal => signal.name !== 'fw');
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
    emul_barrier: 'state', emul_counter: 'load_relay', emul_fire_detector: 'alarm',
    emul_ventilation: 'mode', emul_elevator: 'door', emul_leak_hub: 'leak',
  };
  const preferredSignal = signals.find(signal => signal.name === preferred[device.model]);
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
  if (isBooleanSignal(signal)) return 1;
  if (isEnumSignal(signal)) return Number(Object.keys(signal.layout || {})[0] ?? 0);
  return device?.state?.[signal.name] ?? signal.min ?? 0;
}
function formatRulePhrase(rule: Rule, devices: Device[]) {
  const device = devices.find(item => item.id === rule.device_id);
  const signal = device?.declaration.find(item => item.name === rule.signal);
  if (!signal) return 'выбранное событие';
  const title = signal.title.toLocaleLowerCase('ru-RU');
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
  if (isCommandSignal(signal)) return `${signal.title.toLocaleLowerCase('ru-RU')} (${device?.title.toLocaleLowerCase('ru-RU')})`;
  if (isBooleanSignal(signal)) {
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
  const [builderDevice, setBuilderDevice] = useState<Device | null>(null);
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
    const connect = () => { socket = new WebSocket(wsUrl); socket.onmessage = (msg) => { const e = JSON.parse(msg.data); if (e.type === 'device_state') { setDevices(old => old.map(d => d.id === e.device_id ? { ...d, state: e.state } : d)); setSelected(old => old && old.id === e.device_id ? { ...old, state: e.state } : old); } if (e.type === 'execution') setLogs(old => [e.item, ...old].slice(0,100)); }; socket.onclose = () => { retry = window.setTimeout(connect, 1800); }; };
    connect(); return () => { window.clearTimeout(retry); socket?.close(); };
  }, []);
  const detail = async (id: string) => { try { setSelected(await request<Device>(`/devices/${id}`)); setPage('devices'); } catch (e:any) { notification.error({ message: e.message }); } };
  const command = async (device: Device, signal: Signal, value: any) => { try { await request(`/devices/${device.id}/command/${signal.name}`, { method:'POST', body: JSON.stringify({value}) }); notification.success({message:'Команда выполнена', description:`${signal.title}: ${formatSignalValue(signal,value)}`}); await refresh(); if(selected?.id===device.id) setSelected(await request<Device>(`/devices/${device.id}`)); } catch(e:any) { notification.error({message:'Не удалось изменить сигнал',description:e.message}); } };
  const openBuilder = (device: Device | null = null) => { setBuilderDevice(device); setBuilderOpen(true); };
  const removeDevice = (device: Device) => Modal.confirm({
    title: `Удалить устройство «${device.title}»?`,
    content: 'Устройство будет удалено из списка. Связанные сценарии отключатся, чтобы не запускать команды для отсутствующего устройства.',
    okText: 'Удалить', cancelText: 'Отмена', okType: 'danger',
    onOk: async () => {
      try {
        const result = await request<any>(`/generic-devices/${device.id}`, { method: 'DELETE' });
        const affected = scenarios.filter(scenario=>scenarioUsesDevice(scenario,device.id));
        setDevices(current=>current.filter(item=>item.id!==device.id));
        setScenarios(current=>current.map(scenario=>scenarioUsesDevice(scenario,device.id)?{...scenario,enabled:false}:scenario));
        notification.success({message:'Устройство удалено',description:(result.disabled_scenarios??affected.length) ? `Отключено сценариев: ${result.disabled_scenarios??affected.length}` : undefined});
        setSelected(null); setPage('devices'); await refresh();
      } catch (e:any) { notification.error({message:'Не удалось удалить устройство',description:e.message}); }
    },
  });
  const builderDone = async (updatedDeviceId?: string) => {
    await refresh();
    if (updatedDeviceId) {
      try { setSelected(await request<Device>(`/devices/${updatedDeviceId}`)); }
      catch { /* The refreshed device list remains available if details cannot be reloaded. */ }
    }
  };
  const menu = [{key:'overview',icon:<AppstoreOutlined/>,label:'Обзор'},{key:'devices',icon:<ControlOutlined/>,label:'Устройства'},{key:'scenarios',icon:<DeploymentUnitOutlined/>,label:'Сценарии'},{key:'builder',icon:<ToolOutlined/>,label:'Конструктор'}];
  return <Layout className="app-shell"><Sider width={238} className="side"><div className="brand"><div><b>UJIN</b><span>SMART HOME</span></div></div><Menu mode="inline" selectedKeys={[page]} items={menu} onClick={({key})=>{setPage(key);setSelected(null); if(key==='builder')openBuilder();}}/></Sider><Layout><Header className="topbar"><div><Text className="crumb">ПРОСТРАНСТВО / </Text><Text strong>{menu.find(m=>m.key===page)?.label.toUpperCase() || 'УСТРОЙСТВО'}</Text></div><Space><Tag color="cyan" className="mode-tag">LOCAL</Tag><span className="live-dot"/><Text type="secondary">{devices.length} устройств</Text><Button size="small" onClick={()=>setLiveOpen(true)}>LIVE · {live.configured?'настроен':'настройка'}</Button></Space></Header><Content className="content">
    {page==='overview' && <Dashboard devices={devices} scenarios={scenarios} logs={logs} onOpen={detail} onCreate={()=>openScenarioEditor(null)} />}
    {page==='devices' && <DevicesPage devices={devices} selected={selected} onOpen={detail} onBack={()=>setSelected(null)} onCommand={command} onSimulate={async(d,v)=>{try{await request(`/devices/${d.id}/simulate`,{method:'POST',body:JSON.stringify({signal:'leak',value:v})});await refresh();if(selected)setSelected(await request<Device>(`/devices/${selected.id}`));}catch(e:any){notification.error({message:e.message});}}} onBuild={()=>openBuilder()} onEditDevice={device=>openBuilder(device)} onDeleteDevice={removeDevice} />}
    {page==='scenarios' && <ScenarioPage scenarios={scenarios} devices={devices} logs={logs} onEdit={openScenarioEditor} onRefresh={refresh} />}
    {page==='builder' && <BuilderLanding onOpen={()=>openBuilder()} onDeviceOpen={detail} devices={devices} />}
  </Content></Layout>
  <DeviceBuilder open={builderOpen} device={builderDevice} onClose={()=>{setBuilderOpen(false);setBuilderDevice(null);if(page==='builder')setPage('devices');}} onDone={builderDone}/>
  <LivePanel open={liveOpen} onClose={()=>setLiveOpen(false)} status={live}/>
  {scenarioEditorOpen && <ScenarioEditor scenario={scenarioEdit} devices={devices} onClose={()=>setScenarioEditorOpen(false)} onSaved={()=>{setScenarioEditorOpen(false);setScenarioEdit(null);refresh();setPage('scenarios');}}/>}
  </Layout>;
}

function LivePanel({open,onClose,status}:{open:boolean;onClose:()=>void;status:any}){
  const [serial,setSerial]=useState('');const [signal,setSignal]=useState('');const [value,setValue]=useState('1');const [readDone,setReadDone]=useState(false);const [busy,setBusy]=useState(false);
  const read=async()=>{setBusy(true);try{await request(`/live/devices/${encodeURIComponent(serial)}`);setReadDone(true);}catch(e:any){notification.error({message:'Не удалось прочитать устройство Ujin',description:e.message});}finally{setBusy(false)}};
  const send=async()=>{setBusy(true);try{const parsed=isNaN(Number(value))?value:Number(value);await request(`/live/devices/${encodeURIComponent(serial)}/command`,{method:'POST',body:JSON.stringify({signal,value:parsed})});notification.success({message:'Команда отправлена в Ujin'});}catch(e:any){notification.error({message:'Команда не отправлена',description:e.message});}finally{setBusy(false)}};
  return <Drawer title="Интеграция Ujin · LIVE" width={500} open={open} onClose={onClose}><Alert type={status.configured?'success':'info'} showIcon message={status.configured?'Доступы заданы':'Работаем в LOCAL'} description={status.message}/><Form layout="vertical" style={{marginTop:22}}><Form.Item label="Серийный номер устройства"><Input value={serial} onChange={e=>setSerial(e.target.value)} placeholder="Серийный номер из Ujin"/></Form.Item><Space style={{width:'100%'}}><Button onClick={read} loading={busy} disabled={!serial||!status.configured}>Прочитать устройство</Button></Space><Divider>Отправить команду</Divider><Form.Item label="Параметр устройства"><Input value={signal} onChange={e=>setSignal(e.target.value)} placeholder="Название параметра в Ujin"/></Form.Item><Form.Item label="Значение"><Input value={value} onChange={e=>setValue(e.target.value)}/></Form.Item><Button type="primary" onClick={send} loading={busy} disabled={!serial||!signal||!status.configured}>Отправить команду</Button></Form>{readDone&&<Alert type="success" showIcon message="Данные устройства получены"/>}</Drawer>
}

function Dashboard({devices,scenarios,logs,onOpen,onCreate}:{devices:Device[];scenarios:Scenario[];logs:any[];onOpen:(id:string)=>void;onCreate:()=>void}) {
  return <div className="page-wrap"><div className="hero"><div><Tag color="cyan">SMART BUILDING SIMULATOR</Tag><Title level={2}>Контроль пространства</Title><Text type="secondary">Управляйте виртуальными устройствами и собирайте автоматизации в одном контуре.</Text></div><div className="hero-orb"><div className="orb-grid"/><BulbOutlined/></div></div><Row gutter={[16,16]} className="stats"><Col xs={12} md={6}><Metric label="Устройства" value={devices.length} hint="в локальной сети" icon={<ControlOutlined/>}/></Col><Col xs={12} md={6}><Metric label="Сценарии" value={scenarios.length} hint={`${scenarios.filter(s=>s.enabled).length} активны`} icon={<DeploymentUnitOutlined/>}/></Col><Col xs={12} md={6}><Metric label="Контур" value="LOCAL" hint="работает автономно" icon={<ApiOutlined/>}/></Col><Col xs={12} md={6}><Metric label="События" value={logs.length} hint="в журнале исполнения" icon={<ThunderboltOutlined/>}/></Col></Row><div className="section-head"><div><Title level={4}>Устройства</Title><Text type="secondary">Быстрый доступ к текущему состоянию</Text></div><Button type="primary" icon={<PlusOutlined/>} onClick={()=>onOpen('leak_1')}>Открыть демо</Button></div><Row gutter={[14,14]}>{devices.slice(0,6).map(d=><Col xs={24} sm={12} xl={8} key={d.id}><DeviceCard device={d} onClick={()=>onOpen(d.id)}/></Col>)}</Row><div className="section-head"><div><Title level={4}>Журнал событий</Title><Text type="secondary">Обновляется в реальном времени</Text></div></div><LogList logs={logs.slice(0,5)} scenarios={scenarios}/></div>
}
function Metric({label,value,hint,icon}:{label:string;value:any;hint:string;icon:any}){return <Card className="metric-card"><div className="metric-icon">{icon}</div><Text type="secondary">{label}</Text><div className="metric-number">{value}</div><small>{hint}</small></Card>}
function DeviceCard({device,onClick}:{device:Device;onClick:()=>void}){
  const signal=getPrimarySignal(device);
  const status=signal?formatSignalValue(signal,device.state[signal.name]):'Нет данных';
  return <Card hoverable className="device-card" onClick={onClick}>
    <div className="card-top"><span className="device-glyph"><IconFor model={device.model}/></span><Tag bordered={false} color="green">В сети</Tag></div>
    <Title level={5} className="device-card-title">{device.title}</Title>
    <div className="device-primary-state">{status}</div>
    <div className="card-action">Открыть панель <span>↗</span></div>
  </Card>;
}
function IconFor({model}:{model:string}){return model.includes('leak')?<span>⌁</span>:model.includes('light')?<BulbOutlined/>:model.includes('thermostat')?<span>°</span>:model.includes('barrier')?<span>⌑</span>:<ThunderboltOutlined/>}
function DevicesPage({devices,selected,onOpen,onBack,onCommand,onSimulate,onBuild,onEditDevice,onDeleteDevice}:{devices:Device[];selected:Device|null;onOpen:(id:string)=>void;onBack:()=>void;onCommand:(d:Device,s:Signal,v:any)=>void;onSimulate:(d:Device,v:number)=>void;onBuild:()=>void;onEditDevice:(d:Device)=>void;onDeleteDevice:(d:Device)=>void}){
  if(!selected)return <div className="page-wrap"><div className="section-head page-title"><div><Title level={2}>Устройства</Title><Text type="secondary">Состояния и управление устройствами</Text></div><Button type="primary" icon={<PlusOutlined/>} onClick={onBuild}>Создать устройство</Button></div><Row gutter={[14,14]}>{devices.map(d=><Col xs={24} sm={12} xl={8} key={d.id}><DeviceCard device={d} onClick={()=>onOpen(d.id)}/></Col>)}</Row></div>;
  const groupsOrder=['property','capability','setting'];
  return <div className="page-wrap"><Button type="link" onClick={onBack}>← Все устройства</Button><div className="device-detail-head"><div><Tag color="green">В сети</Tag><Title level={2}>{selected.title}</Title></div><Space wrap>{selected.model==='emul_leak_sensor'&&<><Button onClick={()=>onSimulate(selected,1)}>Сымитировать протечку</Button><Button onClick={()=>onSimulate(selected,0)}>Осушить датчик</Button></>}{selected.model==='generic_device'&&<><Button icon={<ToolOutlined/>} onClick={()=>onEditDevice(selected)}>Изменить устройство</Button><Button danger icon={<DeleteOutlined/>} onClick={()=>onDeleteDevice(selected)}>Удалить</Button></>}</Space></div><Row gutter={16}><Col xs={24} xl={17}>{groupsOrder.map(group=>{const sigs=getVisibleSignals(selected).filter(s=>s.group===group);if(!sigs.length)return null;return <section className="signal-section" key={group}><div className="section-head"><Title level={4}>{groups[group]}</Title><Text type="secondary">{sigs.length} параметров</Text></div><Row gutter={[12,12]}>{sigs.map(s=><Col xs={24} md={12} key={s.name}><SignalCard device={selected} signal={s} value={selected.state[s.name]} onCommand={onCommand}/></Col>)}</Row></section>})}</Col><Col xs={24} xl={7}><Card className="detail-side"><Title level={5}>Сведения</Title><Descriptions column={1} size="small"><Descriptions.Item label="Название">{selected.title}</Descriptions.Item><Descriptions.Item label="Параметров">{getVisibleSignals(selected).length}</Descriptions.Item><Descriptions.Item label="Подключение">Локальное</Descriptions.Item></Descriptions></Card></Col></Row></div>
}
function SignalCard({device,signal,value,onCommand}:{device:Device;signal:Signal;value:any;onCommand:(d:Device,s:Signal,v:any)=>void}){
  const writable=['rw','w'].includes(signal.management);
  const [rangeValue,setRangeValue]=useState(Number.isFinite(Number(value))?Number(value):0);
  useEffect(()=>{setRangeValue(Number.isFinite(Number(value))?Number(value):0);},[value]);
  let editor:any=null;
  const opts=signal.layout?Object.keys(signal.layout).map(v=>({value:Number(v),label:formatSignalValue(signal,v)})):[];
  if(writable){
    if(signal.control==='switch') editor=<Space><Switch checked={!!Number(value)} onChange={v=>onCommand(device,signal,v?1:0)}/><Text>{formatSignalValue(signal,value)}</Text></Space>;
    else if(signal.control==='range') editor=<div className="range-control"><Slider min={signal.min??0} max={signal.max??100} value={rangeValue} onChange={setRangeValue} onChangeComplete={v=>onCommand(device,signal,v)}/><Text>{formatSignalValue(signal,rangeValue)}</Text></div>;
    else if(signal.control==='push_time') editor=<Button type="primary" onClick={()=>onCommand(device,signal,1)}>Выполнить</Button>;
    else if(signal.control==='counter'||signal.control==='number') editor=<InputNumber min={signal.min} max={signal.max} value={Number(value)} onChange={v=>v!==null&&onCommand(device,signal,v)}/>;
    else if(opts.length) editor=<Select value={Number(value)} options={opts} onChange={v=>onCommand(device,signal,v)} style={{minWidth:130}}/>;
    else editor=<Input value={String(value)} onPressEnter={e=>onCommand(device,signal,(e.target as HTMLInputElement).value)}/>;
  }
  return <Card size="small" className="signal-card"><div><Text strong>{signal.title}</Text></div><div className="signal-control">{writable?editor:<b>{formatSignalValue(signal,value)}</b>}</div></Card>;
}
function ScenarioPage({scenarios,devices,logs,onEdit,onRefresh}:{scenarios:Scenario[];devices:Device[];logs:any[];onEdit:(s:Scenario|null)=>void;onRefresh:()=>void}){
  const [helpOpen,setHelpOpen]=useState(false);
  const toggle=async(s:Scenario)=>{try{await request(`/scenarios/${s.id}/${s.enabled?'disable':'enable'}`,{method:'POST'});onRefresh();}catch(e:any){notification.error({message:e.message})}};
  const test=async(s:Scenario)=>{try{await request(`/scenarios/${s.id}/test`,{method:'POST'});notification.success({message:'Тест сценария запущен'});onRefresh();}catch(e:any){notification.error({message:e.message})}};
  return <div className="page-wrap"><div className="section-head page-title"><div><Title level={2}>Сценарии</Title><Text type="secondary">Выберите событие, при необходимости добавьте проверку и задайте действие.</Text></div><Space><Button icon={<QuestionCircleOutlined/>} onClick={()=>setHelpOpen(true)}>Как это работает</Button><Button type="primary" icon={<PlusOutlined/>} onClick={()=>onEdit(null)}>Новый сценарий</Button></Space></div><Row gutter={16}><Col xs={24} xl={15}><Space direction="vertical" size={12} style={{width:'100%'}}>{scenarios.length?scenarios.map(s=><Card className="scenario-card" key={s.id}><div className="scenario-row"><div><Text type="secondary" className="micro">{s.execution_mode==='live'?'ПЛАТФОРМА UJIN':'ЛОКАЛЬНЫЙ СЦЕНАРИЙ'}</Text><Title level={5}>{s.title}</Title><Text>{scenarioSummary(s,devices)}</Text></div><Space wrap><Switch checked={s.enabled} onChange={()=>toggle(s)} checkedChildren="Вкл" unCheckedChildren="Выкл"/><Button onClick={()=>test(s)}>Проверить</Button><Button onClick={()=>onEdit(s)}>Изменить</Button><Button onClick={async()=>{try{await request<any>(`/live/scenarios/${s.id}/deploy`,{method:'POST'});notification.success({message:'Сценарий отправлен в Ujin'});}catch(e:any){notification.error({message:'LIVE недоступен',description:e.message})}}}>В LIVE</Button></Space></div><div className="flow-summary"><Tag color="blue">КОГДА</Tag><span>⟶</span>{(s.condition||s.conditions?.length)&&<><Tag color="gold">ЕСЛИ</Tag><span>⟶</span></>}<Tag color="green">ТОГДА</Tag><span className="flow-line"/></div></Card>):<EmptyCard title="Пока нет сценариев" description="Создайте первое правило автоматизации." onClick={()=>onEdit(null)}/>}</Space></Col><Col xs={24} xl={9}><Card className="log-card"><div className="section-head"><div><Title level={4}>Выполнение</Title><Text type="secondary">Последние события автоматизаций</Text></div><Tag color="cyan">ЖУРНАЛ</Tag></div><LogList logs={logs.slice(0,18)} scenarios={scenarios}/></Card></Col></Row><HelpDrawer open={helpOpen} onClose={()=>setHelpOpen(false)} kind="scenario"/></div>
}
function scenarioSummary(s:Scenario,devices:Device[]){return formatScenarioHumanReadable(s.trigger,s.condition||s.conditions?.[0]||null,s.action||s.actions?.[0],devices);}
function scenarioUsesDevice(scenario:Scenario,deviceId:string){const parts=[scenario.trigger,scenario.condition,...(scenario.conditions||[]),scenario.action,...(scenario.actions||[])].filter(Boolean);return parts.some(part=>part.device_id===deviceId);}
function LogList({logs,scenarios=[]}:{logs:any[];scenarios?:Scenario[]}){return <div className="log-list">{logs.length?logs.map((l,i)=><div className="log-row" key={`${l.time}-${i}`}><i className={`log-dot ${l.node_id||l.status||''}`}/><div><b>{l.message||l.status||'Событие'}</b><small>{new Date(l.time).toLocaleTimeString('ru-RU')} · {scenarios.find(s=>s.id===l.scenario_id)?.title||'Автоматизация'}</small></div></div>):<Text type="secondary">Событий пока нет</Text>}</div>}
function EmptyCard({title,description,onClick}:{title:string;description:string;onClick:()=>void}){return <Card className="empty-card"><div>⌘</div><Title level={4}>{title}</Title><Text type="secondary">{description}</Text><br/><Button type="primary" onClick={onClick}>Создать</Button></Card>}
function BuilderLanding({onOpen,onDeviceOpen,devices}:{onOpen:()=>void;onDeviceOpen:(id:string)=>void;devices:Device[]}){const [helpOpen,setHelpOpen]=useState(false);const customDevices=devices.filter(d=>d.model==='generic_device');return <div className="page-wrap"><div className="section-head page-title"><div><Title level={2}>Конструктор устройств</Title><Text type="secondary">Добавьте виртуальную модель с параметрами без написания кода.</Text></div><Space><Button icon={<QuestionCircleOutlined/>} onClick={()=>setHelpOpen(true)}>Как это работает</Button><Button type="primary" icon={<PlusOutlined/>} onClick={onOpen}>Создать устройство</Button></Space></div>{customDevices.length>0&&<Row gutter={[12,12]}>{customDevices.map(d=><Col xs={24} md={8} key={d.id}><DeviceCard device={d} onClick={()=>onDeviceOpen(d.id)}/></Col>)}</Row>}{customDevices.length===0&&<EmptyCard title="Создайте устройство под свой сценарий" description="Добавленные устройства появятся здесь и будут доступны в автоматизациях." onClick={onOpen}/>}<HelpDrawer open={helpOpen} onClose={()=>setHelpOpen(false)} kind="device"/></div>}

const newParameter = (index: number): Parameter => ({name:`parameter_${index+1}`,title:'',control:'switch',management:'rw',kind:'capability',value:0});
const presets: {label:string;description:string;parameter:Parameter}[] = [
  {label:'Переключатель',description:'Например, свет или реле',parameter:{name:'lamp',title:'Свет',control:'switch',management:'rw',kind:'capability',value:0}},
  {label:'Датчик температуры',description:'Показание в градусах',parameter:{name:'temperature',title:'Температура',control:'number',management:'r',kind:'property',value:20,measure:'°C',min:-20,max:80}},
  {label:'Счётчик',description:'Накопительное показание',parameter:{name:'total',title:'Счётчик',control:'counter',management:'r',kind:'property',value:0,measure:'ед.'}},
  {label:'Команда',description:'Например, открыть заслонку',parameter:{name:'open',title:'Открыть',control:'push_time',management:'w',kind:'capability',value:0}},
];
const controlOptions = Object.entries(typeLabels).filter(([key])=>key!=='graph'&&key!=='button').map(([value,label])=>({value,label}));

function HelpDrawer({open,onClose,kind}:{open:boolean;onClose:()=>void;kind:'scenario'|'device'}){
  const scenario=kind==='scenario';
  return <Drawer title={scenario?'Как создать сценарий':'Как создать виртуальное устройство'} width={440} open={open} onClose={onClose}>
    {scenario?<><Typography.Paragraph>Сценарий связывает событие и действие простыми правилами.</Typography.Paragraph><ol><li><b>Когда</b> — выберите событие, которое запускает автоматизацию.</li><li><b>Если</b> — при необходимости добавьте дополнительную проверку.</li><li><b>Тогда</b> — выберите действие системы.</li></ol><Alert type="info" showIcon message="Например" description="Когда датчик движения обнаружит человека, если темно, включить свет."/></>:<><Typography.Paragraph>Виртуальное устройство состоит из параметров, которые оно сообщает или которыми управляет.</Typography.Paragraph><ul><li><b>Показание</b> — устройство сообщает значение, например температуру.</li><li><b>Состояние</b> — его можно прочитать, например включён ли свет.</li><li><b>Управление</b> — действие, например включить свет.</li><li><b>Настройка</b> — значение конфигурации, например целевая температура.</li></ul><Alert type="info" showIcon message="Параметры устройства" description="Имена и значения параметров настраиваются внутри конструктора."/></>}
  </Drawer>;
}

function DeviceBuilder({open,device,onClose,onDone}:{open:boolean;device:Device|null;onClose:()=>void;onDone:(deviceId?:string)=>void}){
  const [title,setTitle]=useState('');const [rows,setRows]=useState<Parameter[]>([]);const [helpOpen,setHelpOpen]=useState(false);
  useEffect(()=>{if(!open)return;setTitle(device?.title||'');setRows(device?getVisibleSignals(device).map(signal=>({...signal,value:device.state[signal.name]??0})):[]);},[device,open]);
  const update=(index:number,patch:Partial<Parameter>)=>setRows(current=>current.map((row,i)=>i===index?{...row,...patch}:row));
  const add=(parameter?:Parameter)=>setRows(current=>{const row=parameter?{...parameter}:{...newParameter(current.length)};if(current.some(item=>item.name===row.name))row.name=`${row.name}_${current.length+1}`;return [...current,row];});
  const optionsText=(row:Parameter)=>Object.values(row.layout||{}).join(', ');
  const save=async()=>{
    if(!title.trim()||!rows.length||rows.some(row=>!row.title.trim()||!row.name.trim())){
      notification.warning({message:'Заполните название устройства и параметры'});
      return;
    }
    const signals=rows.map(row=>({
      ...row,
      title:row.title.trim(),
      layout:row.control==='list'
        ?Object.fromEntries(optionsText(row).split(',').map(v=>v.trim()).filter(Boolean).map((v,i)=>[i,v]))
        :row.layout,
    }));
    try{
      await request(device?`/generic-devices/${device.id}`:'/generic-devices',{method:device?'PUT':'POST',body:JSON.stringify({title:title.trim(),signals})});
      notification.success({message:device?'Изменения сохранены':'Устройство создано'});
      onDone(device?.id);
      onClose();
    }catch(e:any){
      notification.error({message:'Не удалось создать устройство',description:e.message});
    }
  };
  return <Drawer title={device?'Изменить виртуальное устройство':'Новое виртуальное устройство'} width={620} open={open} onClose={onClose} extra={<Button type="primary" onClick={save} disabled={!title.trim()||!rows.length||rows.some(row=>!row.title.trim()||!row.name.trim())}>{device?'Сохранить изменения':'Сохранить'}</Button>}>
    <div className="builder-step"><span>1</span><div><b>Название</b><small>Как устройство будет называться в приложении.</small></div><Button type="text" icon={<QuestionCircleOutlined/>} onClick={()=>setHelpOpen(true)}>Как это работает</Button></div>
    <Form layout="vertical"><Form.Item label="Название устройства" required><Input size="large" value={title} onChange={e=>setTitle(e.target.value)} placeholder="Например, Лампа в гостиной"/></Form.Item></Form>
    <div className="builder-explainer"><InfoCircleOutlined/><div><b>Параметры устройства</b><p>Параметр — это показание, состояние или команда. Например, температура, включённый свет или команда «Открыть».</p></div></div>
    <div className="builder-presets"><Text strong>Добавить пример</Text><div>{presets.map(p=><Tooltip key={p.label} title={p.description}><Button size="small" onClick={()=>add(p.parameter)}>＋ {p.label}</Button></Tooltip>)}</div></div>
    <div className="section-head builder-section-head"><div><Title level={4}>Параметры</Title><Text type="secondary">{rows.length ? `Добавлено: ${rows.length}` : 'Добавьте первый параметр'}</Text></div></div>
    {!rows.length?<div className="parameter-empty"><div className="parameter-empty-icon">＋</div><b>У устройства пока нет параметров</b><p>Добавьте показание, состояние или команду, чтобы использовать устройство в сценариях.</p><Button type="primary" ghost icon={<PlusOutlined/>} onClick={()=>add()}>Добавить первый параметр</Button></div>:rows.map((row,index)=><Card key={index} className="parameter-card"><div className="parameter-card-heading"><div><Text type="secondary">ПАРАМЕТР {index+1}</Text><b>{row.title||'Новый параметр'}</b></div><Button danger type="text" icon={<DeleteOutlined/>} aria-label="Удалить параметр" onClick={()=>setRows(current=>current.filter((_,i)=>i!==index))}/></div>
      <Form layout="vertical"><Row gutter={12}><Col span={24}><Form.Item label="Название параметра"><Input value={row.title} placeholder="Например, Свет" onChange={e=>update(index,{title:e.target.value})}/></Form.Item></Col><Col xs={24} md={12}><Form.Item label="Роль параметра" extra={roleHelp[row.kind]}><Select value={row.kind} onChange={kind=>update(index,{kind,management:kind==='property'?'r':'rw'})} options={[{value:'property',label:'Показание или состояние'},{value:'capability',label:'Управление устройством'},{value:'setting',label:'Настройка устройства'}]}/></Form.Item></Col><Col xs={24} md={12}><Form.Item label="Тип значения" extra={controlHelp[row.control]}><Select value={row.control} onChange={control=>update(index,{control,min:control==='range'?(row.min??0):row.min,max:control==='range'?(row.max??100):row.max,layout:control==='list'?(row.layout||{0:'Вариант 1',1:'Вариант 2'}):row.layout})} options={controlOptions}/></Form.Item></Col><Col span={24}><Form.Item label="Кто может менять значение?" extra={accessHelp[row.management]}><Select value={row.management} onChange={management=>update(index,{management})} options={Object.entries(accessLabels).map(([value,label])=>({value,label}))}/></Form.Item></Col></Row></Form>
      <Collapse ghost items={[{key:'advanced',label:<span className="advanced-label">Дополнительные настройки</span>,children:<Row gutter={12}>{['number','range','counter'].includes(row.control)&&<><Col span={12}><Form.Item label="Единица измерения"><Input value={row.measure||''} onChange={e=>update(index,{measure:e.target.value})} placeholder="°C, %, кВт·ч"/></Form.Item></Col><Col span={12}><Form.Item label="Минимум и максимум"><Space.Compact block><InputNumber value={row.min} placeholder="Мин." onChange={min=>update(index,{min:min??undefined})}/><InputNumber value={row.max} placeholder="Макс." onChange={max=>update(index,{max:max??undefined})}/></Space.Compact></Form.Item></Col></>}{row.control==='list'&&<Col span={24}><Form.Item label="Варианты списка"><Input value={optionsText(row)} onChange={e=>update(index,{layout:Object.fromEntries(e.target.value.split(',').map(v=>v.trim()).filter(Boolean).map((v,i)=>[i,v]))})} placeholder="Автоматический, Ручной, Выключен"/></Form.Item></Col>}</Row>}]} />
    </Card>)}
    {rows.length>0&&<Button className="add-parameter" block icon={<PlusOutlined/>} onClick={()=>add()}>Добавить параметр</Button>}
    <HelpDrawer open={helpOpen} onClose={()=>setHelpOpen(false)} kind="device"/>
  </Drawer>;
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
  if(isNumericSignal(signal)){const n=Number(value);return Number.isFinite(n)&&(signal.min===undefined||n>=signal.min)&&(signal.max===undefined||n<=signal.max);}
  if(isEnumSignal(signal))return Object.prototype.hasOwnProperty.call(signal.layout,String(value));
  return true;
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
  const groups=[{label:context==='action'?'Доступные действия':'Состояния и показания',options:signals.map(signal=>({value:signal.name,label:signal.title,signal}))}];
  return <Select allowClear disabled={disabled||!signals.length} placeholder={disabled?'Сначала выберите устройство':'Выберите параметр'} value={value||undefined} onChange={onChange} options={groups} optionLabelProp="label" optionRender={({data}:any)=><div className="signal-option"><b>{data.signal.title}</b><small>{data.signal.description||groups[data.signal.group]||'Параметр устройства'}{data.signal.measure?` · ${data.signal.measure}`:''}</small></div>}  popupMatchSelectWidth={false} listHeight={280} placement="bottomLeft" getPopupContainer={node=>node.closest('.ant-modal-content')||document.body} popupClassName="scenario-select-popup"/>;
}
function RuleValueFields({signal,value,operator,onChange,role}:{signal:Signal;value:any;operator:string;onChange:(patch:Partial<Rule>)=>void;role:string}){
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
  if(isBooleanSignal(signal))return <Form.Item label={signal.title}><Select value={Number(value)} onChange={onChange} options={[{value:1,label:'Включить'},{value:0,label:'Выключить'}]}/></Form.Item>;
  if(isEnumSignal(signal))return <Form.Item label={signal.title}><Select value={value===undefined?undefined:Number(value)} onChange={onChange} options={Object.keys(signal.layout||{}).map(v=>({value:Number(v),label:formatSignalValue(signal,v)}))}/></Form.Item>;
  return <Form.Item label={isNumericSignal(signal)?`Установить ${signal.title.toLocaleLowerCase('ru-RU')}`:signal.title} validateStatus={!isValueValid(signal,value)?'error':undefined} help={!isValueValid(signal,value)?`Укажите значение${signal.min!==undefined||signal.max!==undefined?` от ${signal.min??'…'} до ${signal.max??'…'}`:''}.`:undefined}><InputNumber className="action-number" value={value} min={signal.min} max={signal.max} addonAfter={signal.measure||undefined} onChange={v=>onChange(v)} placeholder="Введите значение"/></Form.Item>;
}
function NodeConfig({label,accent,children}:{label:string;accent:string;children:any}){return <Card size="small" className={`node-config-card ${accent}`}><Text className="node-label">{label}</Text><Space direction="vertical" style={{width:'100%'}}>{children}</Space></Card>}
