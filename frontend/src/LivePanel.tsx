import { useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Divider, Drawer, Form, Input, Select, Space, Tag, Typography, notification } from 'antd';
import { request } from './api';

type Props = {
  open: boolean;
  onClose: () => void;
  status: any;
  devices: { id: string; title: string }[];
  onRefresh: () => Promise<void>;
};

export default function LivePanel({ open, onClose, status, devices, onRefresh }: Props) {
  const [deviceId, setDeviceId] = useState('');
  const [serial, setSerial] = useState('');
  const [ext, setExt] = useState('');
  const [signal, setSignal] = useState('');
  const [value, setValue] = useState('1');
  const [remote, setRemote] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const bindings: any[] = status.bindings || [];
  useEffect(() => { if (open) void onRefresh(); }, [open]);

  const action = async (run: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await run(); await onRefresh(); }
    catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };
  const choose = (id: string) => {
    setDeviceId(id); setRemote(null);
    const binding = bindings.find(row => row.device_id === id);
    setSerial(binding?.serialnumber || ''); setExt(binding?.ext_guid || '');
  };
  const bind = () => action(async () => {
    await request(`/live/bindings/${encodeURIComponent(deviceId)}`, {
      method: 'PUT', body: JSON.stringify({ serialnumber: serial.trim(), ext_guid: ext.trim() }),
    });
    notification.success({ message: 'Эмулятор связан с устройством Ujin' });
  });
  const sync = () => action(async () => {
    const result = await request<any>('/live/sync', { method: 'POST' });
    if (result.connected === false) throw new Error('Синхронизация завершена с ошибками. Подробности — у устройств ниже.');
  });
  const read = () => action(async () => {
    setRemote(await request(`/live/devices/${encodeURIComponent(serial.trim())}`));
  });
  const send = () => action(async () => {
    const parsed = value.trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : value;
    await request(`/live/devices/${encodeURIComponent(serial.trim())}/command`, {
      method: 'POST', body: JSON.stringify({ signal, value: parsed }),
    });
    notification.success({ message: 'Ujin принял команду', description: 'Результат исполнения появится после опроса устройства.' });
  });

  return <Drawer title="Интеграция с Ujin OS" width={580} open={open} onClose={onClose}>
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert showIcon type={status.connected === false ? 'error' : status.connected ? 'success' : 'info'}
        message={status.message || 'Проверяем настройки'}
        description={status.configured ? `Квартира ${status.apartment_id}. ${status.running ? 'Автоматический обмен включён.' : ' '}` : ' '}/>
      {error && <Alert type="error" showIcon message={error}/>}
      <Space wrap>
        <Button type="primary" loading={busy} disabled={!status.configured || !bindings.length} onClick={sync}>Синхронизировать</Button>
        <Tag color={status.running ? 'cyan' : 'default'}>{status.running ? 'LIVE' : 'LOCAL'}</Tag>
        {status.last_sync && <Typography.Text type="secondary">Последний обмен: {new Date(status.last_sync).toLocaleTimeString('ru-RU')}</Typography.Text>}
      </Space>
      {bindings.map(binding => <Card size="small" key={binding.device_id}
        title={devices.find(d => d.id === binding.device_id)?.title || binding.device_id}
        extra={<Button type="link" disabled={busy} onClick={() => choose(binding.device_id)}>Выбрать</Button>}>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space><Tag color={binding.connected ? 'green' : binding.error ? 'red' : 'default'}>{binding.connected ? 'Обмен работает' : binding.error ? 'Ошибка обмена' : 'Ожидает обмена'}</Tag><Typography.Text copyable>{binding.serialnumber}</Typography.Text></Space>
          {binding.error && <Typography.Text type="danger">{binding.error}</Typography.Text>}
          {!!binding.readonly_commands?.length && <Alert type="warning" showIcon message="Команды ограничены стендом" description={`Для сигналов ${binding.readonly_commands.join(', ')} организаторы должны разрешить управление (rw/w).`}/>}
          {!!binding.unsupported_signals?.length && <Alert type="warning" message={`Этот интерфейс Ujin принимает числовые сигналы. Не передаются: ${binding.unsupported_signals.join(', ')}`}/>}
          <Button size="small" disabled={busy} onClick={() => action(async () => { await request(`/live/bindings/${encodeURIComponent(binding.device_id)}`, { method: 'DELETE' }); })}>Отключить обмен</Button>
        </Space>
      </Card>)}
    </Space>
    <Divider>Привязка эмулятора</Divider>
    <Form layout="vertical">
      <Form.Item label="Устройство в нашем приложении"><Select value={deviceId || undefined} onChange={choose} placeholder="Выберите эмулятор" options={devices.map(d => ({ value: d.id, label: d.title }))}/></Form.Item>
      <Form.Item label="Серийный номер Ujin"><Input value={serial} onChange={e => { setSerial(e.target.value); setRemote(null); }} placeholder="Из карточки устройства или файла доступов"/></Form.Item>
      <Form.Item label="Внешний ID Ujin"><Input value={ext} onChange={e => setExt(e.target.value)} placeholder="Например, kepka_light_01"/></Form.Item>
      <Space wrap><Button onClick={bind} loading={busy} disabled={!status.configured || !deviceId || !serial || !ext}>Сохранить привязку</Button><Button onClick={read} disabled={!status.configured || !serial || busy}>Прочитать из Ujin</Button></Space>
    </Form>
    {remote && <Descriptions style={{ marginTop: 20 }} title="Показания на платформе" size="small" bordered column={1}
      items={(remote.data?.signals || []).filter((s: any) => !s.redacted).map((s: any) => ({ key: s.name, label: s.title || s.name, children: String(s.state?.value ?? s.value ?? '—') }))}/>}
    <Divider>Проверка команды с платформы</Divider>
    <Form layout="vertical">
      <Form.Item label="Сигнал управления Ujin"><Input value={signal} onChange={e => setSignal(e.target.value)} placeholder="Например, integrations_devices_lamp"/></Form.Item>
      <Form.Item label="Значение"><Input value={value} onChange={e => setValue(e.target.value)}/></Form.Item>
      <Button onClick={send} loading={busy} disabled={!status.configured || !serial || !signal}>Отправить через Ujin</Button>
    </Form>
    <Divider>Журнал обмена</Divider>
    <Space direction="vertical" style={{ width: '100%' }}>
      {(status.logs || []).slice(0, 12).map((row: any, index: number) => <Typography.Text key={`${row.time}-${index}`} type={row.kind === 'error' ? 'danger' : 'secondary'}>
        {new Date(row.time).toLocaleTimeString('ru-RU')} · {devices.find(d => d.id === row.device_id)?.title || 'Ujin'} · {row.message}
      </Typography.Text>)}
      {!status.logs?.length && <Typography.Text type="secondary">Записи появятся после первого обмена.</Typography.Text>}
    </Space>
  </Drawer>;
}
