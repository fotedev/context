import React, { useEffect, useState } from 'react';
import { api } from '../../shared/api';
import { HealthStatus } from '../../shared/types';
import PairDialog from './PairDialog';

/** Health-ping banner. Shows project root + .env state.
 *
 * If the server is down, shows a copyable launch command (zero-native-
 * messaging fallback). If the server is up but no bearer token is stored,
 * renders PairDialog so the user can paste the pairing code.
 */
const ServerStatus: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsPairing, setNeedsPairing] = useState(false);

  const checkHealth = async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
      setError(null);
      chrome.storage.local.get(['auth_token'], (result) => {
        setNeedsPairing(!result.auth_token);
      });
    } catch {
      setHealth(null);
      setError('Server offline. Run `python aggregator.py --serve`');
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  if (error) {
    return (
      <div style={{ marginBottom: '15px', padding: '10px', background: '#ffeeee' }}>
        {error}
      </div>
    );
  }

  return (
    <div style={{ marginBottom: '15px', padding: '10px', background: '#eeffee' }}>
      <p><strong>Status:</strong> Connected</p>
      <p><strong>Root:</strong> {health?.project_root}</p>
      <p><strong>Gemini Key:</strong> {health?.has_gemini_key ? 'Set' : 'Missing'}</p>
      {needsPairing && <PairDialog onPaired={() => setNeedsPairing(false)} />}
    </div>
  );
};

export default ServerStatus;
