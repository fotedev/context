import React, { useState } from 'react';
import { api } from '../../shared/api';

/** GEMINI_API_KEY entry — writes to the tool-root .env via POST /api/env.
 *
 * The server never echoes the key back; it only returns has_gemini_key: bool.
 */
const EnvSetup: React.FC = () => {
  const [key, setKey] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSave = async () => {
    setLoading(true);
    try {
      await api.updateEnv(key);
      setMessage('GEMINI_API_KEY saved successfully.');
      setKey('');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginTop: '15px', padding: '10px', border: '1px solid #ddd' }}>
      <h4>Gemini API Key</h4>
      <input
        type="password"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder="Enter GEMINI_API_KEY"
        style={{ width: '100%', marginBottom: '10px', boxSizing: 'border-box' }}
      />
      <button onClick={handleSave} disabled={loading || !key}>
        {loading ? 'Saving...' : 'Save Key'}
      </button>
      {message && <div style={{ marginTop: '5px', fontSize: '12px' }}>{message}</div>}
    </div>
  );
};

export default EnvSetup;
