import React from 'react';
import ServerStatus from './components/ServerStatus';
import SettingsPanel from './components/SettingsPanel';
import InputManager from './components/InputManager';
import EnvSetup from './components/EnvSetup';

const App: React.FC = () => {
  return (
    <div style={{ width: '360px', padding: '10px', fontFamily: 'sans-serif' }}>
      <h2>Context Tool</h2>
      <ServerStatus />
      <InputManager />
      <SettingsPanel />
      <EnvSetup />
    </div>
  );
};

export default App;
