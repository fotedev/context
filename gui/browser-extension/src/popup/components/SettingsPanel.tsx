import React, { useEffect, useState } from 'react';
import { api } from '../../shared/api';
import { Settings, IgnorePatterns } from '../../shared/types';

/** Full mirror of the Req-10 settings schema with toggles.
 *
 * Reads SettingsResponse.settings (NOT a flat dict — gap 5) and surfaces
 * SettingsResponse.message as a non-blocking toast. Includes a collapsible
 * "Ignore patterns" section bound to GET/PUT /api/ignore (Req 9 / gap 1).
 */
const SettingsPanel: React.FC = () => {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [ignorePatterns, setIgnorePatterns] = useState<string[]>([]);
  const [ignoreSources, setIgnoreSources] = useState<IgnorePatterns['sources'] | null>(null);
  const [showIgnore, setShowIgnore] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const sRes = await api.getSettings();
      setSettings(sRes.settings);
      if (sRes.message) setMessage(sRes.message);

      const iRes = await api.getIgnore();
      setIgnorePatterns(iRes.patterns);
      setIgnoreSources(iRes.sources);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleUpdate = async (newSettings: Partial<Settings>) => {
    if (!settings) return;
    try {
      const res = await api.updateSettings(newSettings);
      setSettings(res.settings);
      setMessage('Settings updated.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  const handleIgnoreUpdate = async () => {
    try {
      await api.updateIgnore(ignorePatterns);
      setMessage('Ignore patterns updated.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  if (loading || !settings) return <div>Loading settings...</div>;

  return (
    <div style={{ marginTop: '15px', padding: '10px', border: '1px solid #ddd' }}>
      <h4>Settings</h4>
      {message && (
        <div style={{ fontSize: '12px', color: 'blue', marginBottom: '10px' }}>{message}</div>
      )}

      <div style={{ marginBottom: '10px' }}>
        <label>
          <input
            type="checkbox"
            checked={settings.gemini_judge}
            onChange={(e) => handleUpdate({ gemini_judge: e.target.checked })}
          />
          {' '}Gemini Judge
        </label>
      </div>

      <div style={{ marginBottom: '10px' }}>
        <label>
          <input
            type="checkbox"
            checked={settings.compact_mode}
            onChange={(e) => handleUpdate({ compact_mode: e.target.checked })}
          />
          {' '}Compact Mode
        </label>
      </div>

      <div style={{ marginBottom: '10px' }}>
        <label>Model Count: </label>
        <select
          value={settings.model_count}
          onChange={(e) => handleUpdate({ model_count: Number(e.target.value) })}
        >
          <option value={2}>2</option>
          <option value={4}>4</option>
        </select>
      </div>

      <div style={{ marginBottom: '10px' }}>
        <label>Output Format: </label>
        <select
          value={settings.output_format}
          onChange={(e) => handleUpdate({ output_format: e.target.value })}
        >
          <option value="md">.md</option>
          <option value="txt">.txt</option>
        </select>
      </div>

      <button onClick={() => setShowIgnore(!showIgnore)}>
        {showIgnore ? 'Hide' : 'Show'} Ignore Patterns
      </button>
      {showIgnore && (
        <div style={{ marginTop: '10px' }}>
          {ignoreSources && ignoreSources['.contextignore'].length > 0 && (
            <p style={{ fontSize: '11px', color: '#888' }}>
              Legacy .contextignore (read-only): {ignoreSources['.contextignore'].join(', ')}
            </p>
          )}
          <textarea
            style={{ width: '100%', height: '100px', boxSizing: 'border-box' }}
            value={ignorePatterns.join('\n')}
            onChange={(e) => setIgnorePatterns(e.target.value.split('\n'))}
          />
          <button onClick={handleIgnoreUpdate}>Save Ignore Patterns</button>
        </div>
      )}
    </div>
  );
};

export default SettingsPanel;
