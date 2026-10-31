import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, theme } from 'antd';
import App from './App';
import './styles.css';
import './styles/ux.css';
import '@xyflow/react/dist/style.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ConfigProvider theme={{ algorithm: theme.darkAlgorithm, token: { colorPrimary: '#39c8ff', colorBgBase: '#08121e', borderRadius: 10, fontFamily: 'Inter, Segoe UI, sans-serif' } }}><App /></ConfigProvider></React.StrictMode>,
);
